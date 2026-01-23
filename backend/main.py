from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from typing import List, Literal, Dict, Optional
from fastapi.middleware.cors import CORSMiddleware
import os
import json
import logging
from dotenv import load_dotenv
from pathlib import Path
import re
import math
from collections import Counter
import asyncio
import pandas as pd
import time
import openai

# load .env (prefer backend/.env located next to this file)
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    _loaded_env = str(env_path)
else:
    # fallback to default lookup (cwd, parent dirs)
    load_dotenv()
    _loaded_env = "(default lookup)"

# optional OpenAI SDK
try:
    import openai
except Exception:
    openai = None

app = FastAPI()

# basic logging: file + console
LOG_PATH = os.path.join(os.path.dirname(__file__), "backend.log")
ORCHESTRATE_LOG_PATH = os.path.join(os.path.dirname(__file__), "orchestrate.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("watchcrew.backend")

# Orchestrator 전용 로거 (orchestrate.log에만 기록)
orchestrate_logger = logging.getLogger("watchcrew.orchestrate")
orchestrate_logger.setLevel(logging.INFO)
orchestrate_handler = logging.FileHandler(ORCHESTRATE_LOG_PATH, encoding="utf-8")
orchestrate_handler.setFormatter(logging.Formatter("%(asctime)s: %(message)s"))
orchestrate_logger.addHandler(orchestrate_handler)
orchestrate_logger.propagate = False  # 부모 로거로 전파 방지

# log whether OPENAI_API_KEY is present (do not log the key itself)
logger.info("OPENAI_API_KEY present: %s", bool(os.getenv("OPENAI_API_KEY")))

# 게임 데이터 row_index 상태 관리 (요청마다 증가)
current_row_index = 328

# 게임 데이터 캐시 (앱 시작 시 한 번만 로드)
_game_data_cache: Optional[pd.DataFrame] = None
_game_file_cache: Optional[str] = None

# 환경변수로 허용할 origin을 설정할 수 있도록 함 (쉼표로 구분)
_allowed = os.getenv(
    "BACKEND_ALLOWED_ORIGINS",
    "http://localhost:8080,http://localhost:3000,https://watchcrew-screen-hai.vercel.app",
)
origins = [o.strip() for o in _allowed.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 팀 ID와 팀 이름 매핑
TEAM_DICT = {
    "HT": "Kia Tigers",
    "SK": "SSG Landers",
    "HH": "Hanhwa Eagles",
    "LT": "Lotte Giants",
    "SS": "Samsung Lions",
    "NC": "NC Dinos",
    "LG": "LG Twins",
    "OB": "Doosan Bears",
    "WO": "Kiwoom Heros",
    "KT": "KT Wiz",
}


class GenerateRequest(BaseModel):
    prompt: str = ""
    team: str = ""


class NewsSummaryRequest(BaseModel):
    game: str  # 예: "250523_HTSS_HT_game"


class AgentCandidate(BaseModel):
    id: str
    name: str  # Nickname
    team: str
    userPrompt: str = ""  # 사용자 입력 프롬프트
    동기: Dict[str, Dict[str, str]] = (
        {}
    )  # 스포츠 시청 동기, 채팅 참여 동기 (각각 example_value, explanation)
    동기요약: str = ""  # 동기 요약 설명
    애착: Dict[str, Dict[str, str]] = (
        {}
    )  # 애착의 대상, 애착의 강도/단계 (각각 example_value, explanation)
    애착요약: str = ""  # 애착 요약 설명


# ============================================
# JSON Parsing Utilities (from orchestration_v2.ipynb)
# ============================================


def extract_codeblock(s: str) -> str:
    """```json ... ``` 구간 추출 (없으면 원문 반환)"""
    m = re.search(r"```json\s*(.*?)\s*```", s, flags=re.DOTALL | re.IGNORECASE)
    return m.group(1) if m else s


def strip_wrapper_quotes(s: str) -> str:
    """양끝의 단일 따옴표 한 쌍 제거 (있을 때만)"""
    return s[1:-1] if len(s) >= 2 and s[0] == s[-1] == "'" else s


def remove_js_comments(s: str) -> str:
    """// 주석 및 /* ... */ 주석 제거"""
    s = re.sub(r"//.*?$", "", s, flags=re.MULTILINE)  # // line comments
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)  # /* block comments */
    return s


def sanitize_trailing_commas_outside_strings(s: str) -> str:
    """문자열(\"...\")은 그대로 두고, 문자열 밖에서만 }, ] 앞의 불필요한 콤마 제거."""
    pattern = r"(\"(?:\\.|[^\"\\])*\")|,\s*([}\]])"
    return re.sub(pattern, lambda m: m.group(1) if m.group(1) else m.group(2), s)


def prepare_json_text(raw: str) -> str:
    """OpenAI 응답에서 JSON 텍스트 추출 및 정리"""
    s = extract_codeblock(raw)
    s = strip_wrapper_quotes(s)
    s = remove_js_comments(s)
    s = sanitize_trailing_commas_outside_strings(s)
    # BOM 제거 등 사소한 정리
    s = s.lstrip("\ufeff").strip()
    return s


# ============================================
# News Summarizer (from orchestration_v2.ipynb)
# ============================================


def news_summarizer(news_dict: dict) -> dict:
    llm = ChatOpenAI(model="gpt-5-mini")
    """전날 뉴스 기사 제목을 요약하는 함수"""
    try:
        openai_key = os.getenv("OPENAI_API_KEY")
        openai_model = os.getenv("OPENAI_MODEL", "gpt-4.1")

        if not openai or not openai_key:
            logger.warning("OpenAI not available for news summarization")
            return {}

        client = openai.OpenAI(api_key=openai_key)

        prompt = f"""
당신은 최근 뉴스를 요약하는 직업입니다. 당신의 역할은 두 팀의 전날 업데이트된 뉴스 기사의 제목을 보고 두 팀의 최근 경기 상황 및 소식을 요약하여 제공해야합니다.

[주어진 데이터]
# News title data from yesterday
: 전날 올라온 두 팀의 뉴스 기사 제목 100개 (팀별 50개)

----------------

[RESPONSE RULES]
- 각 팀별로 전날 올라온 기사 제목(50개)에서 드러나는 최근 경기 흐름/결과/부상·복귀/선발·라인업/트레이드·엔트리/논란·이슈를 요약한다.
- 요약은 제목에서 확인 가능한 내용만 사용하며, 추측·과장·새 사실 생성을 하지 않는다.
- 각 팀 요약은 2 ~ 5문장으로 작성하고, 문장마다 다른 핵심 포인트를 담는다.
- 각 팀 요약 내부에서 중복 문장/동일 의미 반복을 피한다.
- 각 팀 요약 내부에 서로 모순되는 내용이 없도록 한다.
- 출력은 반드시 [OUTPUT FORMAT]의 JSON 객체를 따르며, 키는 팀 이름 2개만 포함한다.
- JSON 값(value)은 문자열(string) 로 작성한다.

----------------

[INPUT FORMAT]
# News title data from yesterday
: {news_dict}

[OUTPUT FORMAT]
{{
    name of team1: A summary of the team1's recent performance and key updates,
    name of team2: A summary of the team2's recent performance and key updates
}}

"""
        chatResult = llm.invoke(prompt).content

        clean = prepare_json_text(chatResult)
        recNews = json.loads(clean)

        return recNews
    except Exception as e:
        logger.exception(f"Error in news_summarizer: {e}")
        return {}


# ============================================
# Hardcoded Agent Personas (from orchestration_v2.ipynb)
# TODO: 추후 AgentCreator에서 생성된 데이터를 전달받도록 수정
# ============================================

HARDCODED_AGENTS = [
    {
        "userName": "라이온스밈헌터",
        "team": "samsung",
        "팬의 특성": {
            "스포츠 시청 동기": "오락(재미를 위한 관람)",
            "채팅 참여 동기": "밈 공유·웃기기",
        },
        "애착": {
            "애착의 대상": "종목 자체(야구)",
            "애착의 강도/단계": "흥미(Attraction)",
        },
        "채팅 특성": {
            "Attribution of Responsibility": "선수 개인(퍼포먼스·노력)에 대한 비판",
            "Target of Evaluation": "수비 및 주루 실수",
            "Evaluative Focus": "과정 중심의 전술적 조롱",
            "Use of Numerical/Technical Signals": "비수치적 직관적 주장",
        },
        "표현": {
            "Tone and Linguistic Style": "유머·밈 기반 조롱",
            "Temporal Reactivity": "마이크로 액션에 대한 단발적·짧은 반응",
            "Collective Action Calls": "농담 섞인 선수 강등/교체 요구",
            "Polarity toward Same Target": "칭찬과 비판을 번갈아 사용하는 풍자적 태도",
        },
    },
    {
        "userName": "삼성풍자단",
        "team": "samsung",
        "팬의 특성": {
            "스포츠 시청 동기": "사회적 교류(친목)",
            "채팅 참여 동기": "감정·생각 공유(공동 웃음 유도)",
        },
        "애착": {
            "애착의 대상": "지역/커뮤니티(구단 연고지)",
            "애착의 강도/단계": "충성심(Allegiance)",
        },
        "채팅 특성": {
            "Attribution of Responsibility": "구단 운영·경영진 비판(풍자적 책임 전가)",
            "Target of Evaluation": "감독의 전술 및 라인업 선택",
            "Evaluative Focus": "결과 서술에 감정적·서사적 강조(풍자적 재구성)",
            "Use of Numerical/Technical Signals": "수치와 감정 혼합(Mixed numeric + emotive)",
        },
        "표현": {
            "Tone and Linguistic Style": "유머·밈 기반 풍자(집단적 농담)",
            "Temporal Reactivity": "경기 전반에 걸쳐 지속되는 서사적 풍자",
            "Collective Action Calls": "구조적 개편 요구를 패러디 형태로 제안",
            "Polarity toward Same Target": "과도한 악플·공격을 통제하는 유머적 규범 강조",
        },
    },
    {
        "userName": "라이온스조크박스",
        "team": "samsung",
        "팬의 특성": {
            "스포츠 시청 동기": "흥분·스릴(경기 자체의 재미)",
            "채팅 참여 동기": "감정 공유·즉흥 반응",
        },
        "애착": {
            "애착의 대상": "팀(삼성 라이온즈)",
            "애착의 강도/단계": "애착(Attachment)",
        },
        "채팅 특성": {
            "Attribution of Responsibility": "선수 개인 행동에 대한 즉각적 비난(유머 섞음)",
            "Target of Evaluation": "투수진 성적 및 경기 운영(투구·불펜)",
            "Evaluative Focus": "결과 중심의 단도직입적 평결",
            "Use of Numerical/Technical Signals": "간단한 기술 약어·속기 표현(Technical shorthand/labels)",
        },
        "표현": {
            "Tone and Linguistic Style": "유머·밈 기반의 조롱(짧고 임팩트 있게)",
            "Temporal Reactivity": "극적인 순간에 폭발하는 스파이크 반응",
            "Collective Action Calls": "농담 섞인 선수 교체·강등 요구",
            "Polarity toward Same Target": "지속적 비판 성향(일관된 풍자)",
        },
    },
    {
        "userName": "삼성유머중계",
        "team": "samsung",
        "팬의 특성": {
            "스포츠 시청 동기": "사회적 교류(관전 파티·중계 공유)",
            "채팅 참여 동기": "정보 제공 및 웃음 유발(설명+개그)",
        },
        "애착": {
            "애착의 대상": "팀(삼성 라이온즈)",
            "애착의 강도/단계": "인지 단계(Awareness)",
        },
        "채팅 특성": {
            "Attribution of Responsibility": "운영·전술에 대한 실행 처방(풍자적 제안)",
            "Target of Evaluation": "선수 이적·가치(트레이드·연봉)",
            "Evaluative Focus": "성과와 전술을 혼합해 설명(혼합적·전술적 정당화)",
            "Use of Numerical/Technical Signals": "명시적 통계 활용(Explicit statistics and counts)",
        },
        "표현": {
            "Tone and Linguistic Style": "분석적·테크니컬한 어조에 유머를 얹음",
            "Temporal Reactivity": "즉각적 칭찬 후 빠른 반전(농담 소재화)",
            "Collective Action Calls": "게임 내 전술적 요구를 패러디 형태로 제시",
            "Polarity toward Same Target": "동시에 칭찬과 비판을 오가는 풍자적 태도",
        },
    },
    {
        "userName": "블랙코미디라이온",
        "team": "samsung",
        "팬의 특성": {
            "스포츠 시청 동기": "기분전환·도피(Diversion)",
            "채팅 참여 동기": "감정 해소(유머로 풀기)",
        },
        "애착": {
            "애착의 대상": "종목 자체(야구)",
            "애착의 강도/단계": "인지 단계(Awareness)",
        },
        "채팅 특성": {
            "Attribution of Responsibility": "구단 운영·소유주에 대한 풍자적 비난",
            "Target of Evaluation": "수비·주루 실수 및 경기 운영 미스",
            "Evaluative Focus": "과정 중심의 전술적 비판(풍자적으로 과장)",
            "Use of Numerical/Technical Signals": "비수치적 직관·과장된 묘사",
        },
        "표현": {
            "Tone and Linguistic Style": "다소 신랄한 유머·블랙코미디 스타일의 조롱",
            "Temporal Reactivity": "극적인 장면에서 폭발하는 스파이크 반응",
            "Collective Action Calls": "과장된 방식으로 선수 교체·해체를 요구(풍자)",
            "Polarity toward Same Target": "일관된 조롱·비판적 관점",
        },
    },
]


# ============================================
# Game Data Loader (from orchestration_v2.ipynb Pre data & Stimulus data)
# ============================================


def load_game_data(
    game_file: str = "250523_HTSS_HT_game.csv", row_index: int = 328
) -> tuple:
    """
    backend/game 폴더에서 CSV 파일을 로드하고 특정 행에서
    currGameStat과 gameFlow를 추출합니다.

    캐싱 전략:
    - 같은 game_file이면 메모리 캐시된 DataFrame 재사용
    - 다른 파일 요청 시에만 새로 로드

    orchestration_v2.ipynb의 로직:
    i = 361
    curr_game_stat = df.loc[i, 'currGameStat']
    game_flow = df.loc[i, 'gameFlow']

    Args:
        game_file: CSV 파일명 (기본값: 250523_HTSS_HT_game.csv)
        row_index: 추출할 행 번호 (기본값: 361)

    Returns:
        tuple: (currGameStat, gameFlow, df)
    """
    global _game_data_cache, _game_file_cache

    try:
        game_path = Path(__file__).resolve().parent / "game" / game_file

        if not game_path.exists():
            logger.warning(f"Game file not found: {game_path}, using default data")
            return "경기 진행 중", "경기 흐름 데이터 없음", None

        # 캐시 확인: 같은 파일이면 캐시된 DataFrame 사용
        if _game_file_cache == game_file and _game_data_cache is not None:
            df = _game_data_cache
            logger.debug(f"Using cached game data for {game_file}")
        else:
            # CSV 파일 로드 (처음이거나 다른 파일 요청 시)
            logger.info(f"Loading game data from {game_file}...")
            load_start = time.time()
            df = pd.read_csv(game_path, encoding="utf-8-sig")

            if df.empty:
                logger.warning(f"Game data is empty: {game_path}")
                return "경기 진행 중", "경기 흐름 데이터 없음", df

            # 중복 제거 (orchestration_v2.ipynb 참고)
            df = df.drop_duplicates("messageTime").reset_index(drop=True)

            # 캐시 저장
            _game_data_cache = df
            _game_file_cache = game_file

            load_time = time.time() - load_start
            logger.info(
                f"Loaded and cached game data from {game_file} in {load_time:.3f}s ({len(df)} rows)"
            )

        # 지정된 행 번호가 유효한지 확인
        if row_index < 0 or row_index >= len(df):
            logger.warning(
                f"Row index {row_index} out of bounds (total rows: {len(df)}), using last row"
            )
            row_index = len(df) - 1

        # 특정 행에서 데이터 추출 (orchestration_v2.ipynb 로직)
        selected_row = df.loc[row_index]

        # currGameStat: 현재 경기 상태
        curr_game_stat = str(selected_row.get("currGameStat", "경기 진행 중"))

        # gameFlow: 경기 흐름
        game_flow = str(
            selected_row.get(
                "gameFlow", selected_row.get("seqDescription", "경기 흐름 데이터 없음")
            )
        )

        logger.debug(f"Retrieved row {row_index} from cached data")
        logger.debug(f"Current game stat: {curr_game_stat}")
        logger.debug(f"Game flow: {game_flow[:100]}...")  # 첫 100자만 로그

        return curr_game_stat, game_flow, df

    except Exception as e:
        logger.exception(f"Error loading game data: {e}")
        return "경기 진행 중", "경기 흐름 데이터 없음", None


# ============================================
# Agent Candidate normalization
# ============================================


def _clean_attr_dict(raw: dict, summary_keys: List[str]) -> tuple:
    """Helper to extract a summary string and ensure all other values are Dict[str, str]."""
    cleaned = {}
    summary = ""
    if not isinstance(raw, dict):
        return {}, ""

    # Copy to avoid mutating original
    temp_raw = dict(raw)

    # 1. Extract summary if present in this dict
    for sk in summary_keys:
        if sk in temp_raw:
            val = temp_raw.pop(sk)
            if not summary and isinstance(val, (str, bytes)):
                summary = str(val)

    # 2. Normalize remaining keys
    for k, v in temp_raw.items():
        if isinstance(v, dict):
            # Ensure example_value and explanation exist
            cleaned[k] = {
                "example_value": str(v.get("example_value", v.get("label", ""))),
                "explanation": str(v.get("explanation", "")),
            }
        elif isinstance(v, str):
            # LLM flattened it
            cleaned[k] = {"example_value": v, "explanation": ""}
        else:
            # Fallback for unexpected types
            cleaned[k] = {"example_value": str(v), "explanation": ""}

    return cleaned, summary


def normalize_candidates(
    parsed: List[dict], team: str = "samsung", want_count: int = 5
) -> List[dict]:
    """Normalize and validate parsed candidates from OpenAI.

    Ensures:
    - id format: team-N (auto-assigns sequentially)
    - team is set to the provided team parameter
    - no duplicate ids
    - result count = want_count (pads or truncates)
    """
    counter = 1
    seen = set()
    out = []

    for item in parsed:
        # Generate normalized id based on team and counter
        base_id = f"{team}-{counter}"
        counter += 1

        # Ensure uniqueness by adding suffix if needed
        new_id = base_id
        k = 1
        while new_id in seen:
            new_id = f"{base_id}-{k}"
            k += 1
        seen.add(new_id)

        # Extract name (Nickname)
        user_name = str(
            item.get("Nickname")
            or item.get("name")
            or item.get("userName")
            or f"{team.title()}Fan{counter}"
        )

        # Extract new structure: 팬의 특성 → {동기, 애착}
        fan_traits = item.get("팬의 특성") or {}
        if not isinstance(fan_traits, dict):
            fan_traits = {}

        # 동기: {스포츠 시청 동기: {example_value, explanation}, 채팅 참여 동기: {...}}
        motivations_raw = fan_traits.get("동기") or {}
        motivations, motiv_sum = _clean_attr_dict(
            motivations_raw, ["동기 요약", "동기요약"]
        )
        motivation_summary = (
            motiv_sum or fan_traits.get("동기 요약") or fan_traits.get("동기요약") or ""
        )

        # 애착: {애착의 대상: {example_value, explanation}, 애착의 강도/단계: {...}}
        attachment_raw = fan_traits.get("애착") or {}
        attachment, attach_sum = _clean_attr_dict(
            attachment_raw, ["애착 요약", "애착요약"]
        )
        attachment_summary = (
            attach_sum
            or fan_traits.get("애착 요약")
            or fan_traits.get("애착요약")
            or ""
        )

        out.append(
            {
                "id": new_id,
                "name": user_name,
                "team": team,
                "userPrompt": "",  # Will be set by the caller
                "동기": motivations,
                "동기요약": motivation_summary,
                "애착": attachment,
                "애착요약": attachment_summary,
            }
        )

        if len(out) >= want_count:
            break

    # Pad with empty entries if needed to reach want_count
    while len(out) < want_count:
        new_id = f"{team}-{counter}"
        counter += 1

        if new_id not in seen:
            seen.add(new_id)
            auto_name = f"자동생성{counter}"
            out.append(
                {
                    "id": new_id,
                    "name": auto_name,
                    "team": team,
                    "userPrompt": "",
                    "동기": {},
                    "동기요약": "",
                    "애착": {},
                    "애착요약": "",
                    "내용": {},
                    "채팅내용설명": "",
                    "표현": {},
                    "채팅표현설명": "",
                }
            )

    return out[:want_count]


def transform_agent_for_orchestrate(agent: Dict) -> Dict:
    """localStorage 에이전트를 orchestrate용으로 변환

    제외할 필드:
    - id, avatarSeed, createdAt, isHome, userPrompt
    - 동기요약, 애착요약, 채팅내용설명, 채팅표현설명

    유지할 필드:
    - name → userName
    - team
    - 동기, 애착, 내용, 표현 (dict 형식)
    """
    result = {
        "userName": agent.get("name", "DefaultAgent"),
        "team": agent.get("team", "samsung"),
    }

    # 팬의 특성 구성
    fan_traits = {}

    # 동기 및 애착
    motivation = agent.get("동기", {})
    attachment = agent.get("애착", {})

    if motivation or attachment:
        fan_traits["동기"] = motivation if motivation else {}
        fan_traits["애착"] = attachment if attachment else {}

    if fan_traits:
        result["팬의 특성"] = fan_traits

    # 채팅 특성 구성
    chat_traits = {}

    # 내용 및 표현
    content = agent.get("내용", {})
    expression = agent.get("표현", {})

    if content or expression:
        chat_traits["내용"] = content if content else {}
        chat_traits["표현"] = expression if expression else {}

    if chat_traits:
        result["채팅 특성"] = chat_traits

    return result


def make_tuning_prompt(user_team: str, user_request: str) -> str:
    output_schema = {
        "Nickname": "string",
        "팬의 특성": {
            "동기": {
                "스포츠 시청 동기": {
                    "example_value": "string",
                    "explanation": "string",
                },
                "채팅 참여 동기": {"example_value": "string", "explanation": "string"},
            },
            "동기 요약": "string",
            "애착": {
                "애착의 대상": {"example_value": "string", "explanation": "string"},
                "애착의 강도/단계": {
                    "example_value": "string",
                    "explanation": "string",
                },
            },
            "애착 요약": "string",
        },
    }

    # Format the schema as a clean JSON string for the prompt
    output_format_str = json.dumps(output_schema, indent=2, ensure_ascii=False)

    return f"""
당신은 사용자의 요구사항을 기반으로 야구 팬 페르소나를 커스터마이징하는 페르소나 제작자(Persona Generator)입니다.
사용자 요구사항이 주어지면, 주어진 Attribute–Example Values 세트를 커스터마이징하여 사용자에게 적합한 야구 팀 팬 페르소나 5개를 생성하세요.

────────────────

[주어진 데이터]
- 사용자 선호 야구 팀: {user_team}
- 사용자 요구사항: {user_request}
- Attribute–Example Values set:
  · Attribute: 야구 팬의 특성을 설명하는 상위 카테고리
  · Example Values: 각 Attribute에 대응하는 구체적 특성 값
  · Explanation: 각 Example Value의 의미 설명

────────────────

[RESPONSE RULES]
- 출력은 반드시 [OUTPUT FORMAT]을 따르며, 전체 출력은 JSON list 1개(정확히 5개 object)입니다.
- dv_set에 없는 Attribute를 새로 만들지 마세요.
- 각 속성은 dv_set의 Example Value 라벨 중 하나를 선택하고, explanation은 사용자 요구사항을 반영해 새로 작성하세요.
- 하나의 페르소나 내에서 선택된 모든 Attribute-Example Values set 조합은 의미적으로 서로 모순되지 않아야 합니다.
- 모든 출력은 한국어로 작성하세요.
- 아래 2개의 요약 필드는 각각 1문장으로 작성하세요:
  1) "동기 요약": "스포츠 시청 동기" + "채팅 참여 동기"를 종합
  2) "애착 요약": "애착의 대상" + "애착의 강도/단계"를 종합
- 공격적·모욕적 표현 금지(밈/드립은 가능하나 누구를 지목해 조롱하지 않기).

[IMPORTANT: 값 출력 형식]
- 각 속성 값은 반드시 아래 형태의 JSON object로 출력하세요.
  {{ "example_value": "라벨", "explanation": "선택한 example_value가 사용자 요구사항에서 어떻게 드러나는지를 설명하는 1문장" }}

────────────────

[NICKNAME DESIGN RULES]
닉네임은 단순한 이름이 아니라, 팬의 성향을 암시하는 “압축된 신호”입니다.

- 아래 단서 중 1~2개를 자연스럽게 반영하세요.
  · 팀/야구가 맥락: {user_team} 또는 팀을 연상시키는 야구 관련 표현
  · 성향 단서: 웃음, 풍자, 드립, 편파 없는 관찰자 시선
  · 말투/리듬: 짧은 말장난이나 리듬감 있는 표현
  · 취향 단서: 대표적인 야구 용어 1개 내외

- 공격적·모욕적 표현은 금지하며, “상황을 웃기는 해설자/관찰자” 프레임을 유지하세요.
- 특정 개인(선수·심판·팬)을 지목해 조롱하지 마세요.
- Nickname은 해당 페르소나의 다른 Attribute들과 논리적으로 연결되어야 합니다.

[닉네임 형식 제약]
- 길이: 한글 2~8자 / 영문·숫자 4~10자
- 특수문자·이모지·개인정보(이름·연도·지역) 사용 금지
- 비속어·혐오 표현 금지

[닉네임 다양성]
- 5개 페르소나의 닉네임은 서로 다른 스타일이어야 합니다.

────────────────

[OUTPUT FORMAT]
[
  {output_format_str},
  ... (총 5개)
]
""".strip()


@app.post("/generate_candidates", response_model=List[AgentCandidate])
def generate_candidates(payload: GenerateRequest):
    """페르소나 후보 생성 엔드포인트."""
    userPrompt = payload.prompt or ""
    userTeam = payload.team or "samsung"  # default to samsung if not provided

    # Check if OpenAI SDK and API key are available
    openai_key = os.getenv("OPENAI_API_KEY")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    if not openai or not openai_key:
        raise HTTPException(
            status_code=500,
            detail="OpenAI API not configured. Please set OPENAI_API_KEY environment variable.",
        )

    try:
        openai.api_key = openai_key

        # Support both old openai (0.28) and new openai>=1.0 interfaces.
        if hasattr(openai, "OpenAI"):
            # new interface
            client = openai.OpenAI(api_key=openai_key)
            tuning_prompt = make_tuning_prompt(
                user_team=userTeam, user_request=userPrompt
            )
            resp = client.chat.completions.create(
                model=openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": "Return ONLY valid JSON. Generating results in Korean.",
                    },
                    {"role": "user", "content": tuning_prompt},
                ],
            )
        else:
            # old interface
            tuning_prompt = make_tuning_prompt(
                user_team=userTeam, user_request=userPrompt
            )
            resp = openai.ChatCompletion.create(
                model=openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": "Return ONLY valid JSON. Generating results in Korean.",
                    },
                    {"role": "user", "content": tuning_prompt},
                ],
            )

        # Try multiple ways to extract text from response (dict-like or object-like)
        text = None
        try:
            # dict-like response
            if isinstance(resp, dict):
                text = resp.get("choices", [])[0].get("message", {}).get("content")
            else:
                # object response from new SDK
                choices = getattr(resp, "choices", None)
                if choices and len(choices) > 0:
                    first = choices[0]
                    msg = getattr(first, "message", None)
                    if msg is not None:
                        content = getattr(msg, "content", None)
                        if isinstance(content, list) and len(content) > 0:
                            elem = content[0]
                            # elem may be dict-like or object-like
                            if isinstance(elem, dict):
                                text = elem.get("text")
                            else:
                                text = getattr(elem, "text", None)
                        else:
                            # fallback: maybe message.content is a plain string
                            text = content or getattr(msg, "content", None)
        except Exception:
            text = None

        if not text:
            # final fallback: string representation
            try:
                text = str(resp)
            except Exception:
                text = ""

        # Log the full response for debugging
        logger.debug(f"OpenAI raw response (first 2000 chars): {text[:2000]}")
        if len(text) > 2000:
            # Save full response to file for inspection
            try:
                with open(
                    os.path.join(os.path.dirname(__file__), "openai_response.txt"),
                    "w",
                    encoding="utf-8",
                ) as f:
                    f.write(text)
                logger.debug("Full response saved to openai_response.txt")
            except Exception as e:
                logger.debug(f"Could not save response to file: {e}")

        # Try to parse JSON directly
        try:
            parsed = json.loads(text)
        except Exception as e:
            # Attempt to extract JSON substring with more robust regex
            import re

            logger.debug(f"JSON parse failed, attempting extraction. Error: {e}")

            json_str = None

            # Try to extract from markdown code blocks first (```json ... ```)
            if not json_str:
                m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
                if m:
                    json_str = m.group(1).strip()
                    logger.debug(
                        f"Extracted JSON from markdown code block (length={len(json_str)})"
                    )

            # Try multiple regex patterns to find JSON array
            patterns = [
                r"\[\s*\{[\s\S]*\}\s*\]",  # Greedy: [ ... ] with { } objects
                r"\[[\s\S]*\]",  # Just find any array brackets
            ]

            for pattern in patterns:
                if json_str:
                    break
                m = re.search(pattern, text)
                if m:
                    json_str = m.group(0)
                    logger.debug(
                        f"Extracted JSON with pattern '{pattern}' (length={len(json_str)})"
                    )
                    break

            if json_str:
                try:
                    parsed = json.loads(json_str)
                except Exception as e2:
                    logger.debug(f"Direct parse failed: {e2}, attempting fixes")

                    # Try to fix common JSON issues
                    # 1. Replace smart quotes with regular quotes first
                    json_str = (
                        json_str.replace('"', '"')
                        .replace('"', '"')
                        .replace(
                            """, "'")
                        .replace(""",
                            "'",
                        )
                        .replace("–", "-")
                        .replace("—", "-")
                    )
                    # 2. Remove any control characters that might break JSON
                    json_str = "".join(
                        c for c in json_str if ord(c) >= 32 or c in "\n\r\t"
                    )
                    # 3. Try to fix unclosed strings by finding patterns
                    # Count quotes to detect unclosed strings
                    in_string = False
                    fixed_chars = []
                    i = 0
                    while i < len(json_str):
                        c = json_str[i]
                        if c == '"' and (i == 0 or json_str[i - 1] != "\\"):
                            in_string = not in_string
                            fixed_chars.append(c)
                        elif c in "\n\r" and in_string:
                            # Skip newlines inside strings
                            fixed_chars.append(" ")
                        else:
                            fixed_chars.append(c)
                        i += 1
                    json_str = "".join(fixed_chars)

                    # 4. Handle trailing braces issues (e.g., }}} followed by , or ])
                    # Replace triple closing braces with double if they look like candidate closers
                    json_str = re.sub(r"\}\s*\}\s*\}\s*,", "}},", json_str)
                    json_str = re.sub(r"\}\s*\}\s*\}\s*\]", "}}]", json_str)

                    # 5. Remove trailing commas before closing braces/brackets
                    json_str = re.sub(r",\s*([\]}])", r"\1", json_str)

                    try:
                        parsed = json.loads(json_str)
                        logger.info("Successfully parsed JSON after fixes")
                    except Exception as e3:
                        logger.error(f"Post-fix JSON parse failed. Error: {e3}")
                        # If still failing, try a more aggressive extraction of objects
                        try:
                            # Find all blocks starting with {"Nickname" and ending with }} before a , or ]
                            candidate_matches = re.findall(
                                r'\{"Nickname":[\s\S]*?\}\s*\}', json_str
                            )
                            if candidate_matches:
                                candidates = []
                                for cand_str in candidate_matches:
                                    try:
                                        cand_str_fixed = re.sub(
                                            r",\s*([\]}])", r"\1", cand_str
                                        )
                                        candidates.append(json.loads(cand_str_fixed))
                                    except:
                                        continue
                                if len(candidates) >= 1:
                                    parsed = candidates
                                    logger.info(
                                        f"Successfully extracted {len(candidates)} candidates via regex"
                                    )
                                else:
                                    raise e3
                            else:
                                raise e3
                        except Exception:
                            logger.error(f"All JSON parse attempts failed: {e3}")
                            logger.debug(f"Problematic JSON string: {json_str[:1000]}")
                            raise e3
            else:
                logger.error(
                    f"Could not find JSON array in response. Full response length={len(text)}"
                )
                logger.debug(f"Response preview (first 1000 chars): {text[:1000]}")
                logger.debug(f"Response preview (last 500 chars): {text[-500:]}")
                raise Exception("No JSON array found in OpenAI response")

        # Validate structure minimally and coerce to expected types
        output: List[dict] = []
        for item in parsed:
            try:
                # Keep the raw structure from OpenAI - normalize_candidates will handle it
                # Just ensure it's a dict
                if isinstance(item, dict):
                    output.append(item)
            except Exception:
                logger.exception("invalid item from openai, skipping")

        # Normalize candidates to ensure proper id format, uniqueness, team assignment
        normalized = normalize_candidates(output, team=userTeam, want_count=5)

        # Add userPrompt to all candidates
        for candidate in normalized:
            candidate["userPrompt"] = userPrompt

        if len(normalized) >= 1:
            logger.info("Returning %d candidates from OpenAI", len(normalized))
            # Dump full normalized payload to console/log for inspection
            try:
                logger.info(
                    "Normalized candidates:\n%s",
                    json.dumps(normalized, ensure_ascii=False, indent=2),
                )
            except Exception:
                logger.info("Normalized candidates (raw): %s", normalized)
            return normalized
        else:
            # Parsed but got no valid candidates after normalization
            raise HTTPException(
                status_code=500,
                detail="Failed to generate valid candidates from OpenAI response",
            )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.exception("OpenAI call failed")
        raise HTTPException(
            status_code=500, detail=f"Failed to generate candidates: {str(e)}"
        )


@app.post("/generate_candidates_stream")
async def generate_candidates_stream(payload: GenerateRequest):
    """에이전트 후보를 스트리밍으로 반환하는 엔드포인트 (Server-Sent Events)."""
    userPrompt = payload.prompt or ""
    userTeam = payload.team or "samsung"

    openai_key = os.getenv("OPENAI_API_KEY")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    if not openai or not openai_key:
        raise HTTPException(
            status_code=500,
            detail="OpenAI API not configured. Please set OPENAI_API_KEY environment variable.",
        )

    async def event_generator():
        """스트리밍 이벤트 생성 제너레이터"""
        try:
            openai.api_key = openai_key

            # 클라이언트가 스트림을 바로 인식할 수 있도록 초기 keep-alive 전송
            yield "data: [START]\n\n"
            await asyncio.sleep(0.05)
            # incremental state for object boundary detection
            state = {
                "in_array": False,
                "brace_depth": 0,
                "in_string": False,
                "escape": False,
                "current": "",
            }

            parsed_raw: List[dict] = []

            def extract_content(chunk) -> str:
                """Extract text delta from both old/new OpenAI SDK chunks."""
                try:
                    # new SDK object
                    delta = chunk.choices[0].delta
                    content = getattr(delta, "content", None)
                    if isinstance(content, list):
                        return "".join(
                            (
                                elem.get("text", "")
                                if isinstance(elem, dict)
                                else getattr(elem, "text", "") or ""
                            )
                            for elem in content
                        )
                    if content:
                        return content
                except Exception:
                    pass

                try:
                    # old SDK dict-like
                    return (
                        chunk.get("choices", [])[0].get("delta", {}).get("content", "")
                    )
                except Exception:
                    return ""

            def feed_and_collect(text: str) -> List[str]:
                """Collect complete top-level JSON objects inside array as soon as they close."""
                objects: List[str] = []
                for ch in text:
                    if state["escape"]:
                        state["current"] += ch
                        state["escape"] = False
                        continue

                    if ch == "\\" and state["in_string"]:
                        state["current"] += ch
                        state["escape"] = True
                        continue

                    if ch == '"':
                        state["in_string"] = not state["in_string"]
                        state["current"] += ch
                        continue

                    if not state["in_array"]:
                        if ch == "[":
                            state["in_array"] = True
                        continue

                    if state["brace_depth"] == 0:
                        if ch in " \t\r\n,":
                            continue
                        if ch == "{":
                            state["brace_depth"] = 1
                            state["current"] = "{"
                        elif ch == "]":
                            state["in_array"] = False
                        continue

                    state["current"] += ch

                    if not state["in_string"]:
                        if ch == "{":
                            state["brace_depth"] += 1
                        elif ch == "}":
                            state["brace_depth"] -= 1
                            if state["brace_depth"] == 0:
                                objects.append(state["current"])
                                state["current"] = ""
                return objects

            # OpenAI streaming call
            tuning_prompt = make_tuning_prompt(
                user_team=userTeam, user_request=userPrompt
            )

            if hasattr(openai, "OpenAI"):
                client = openai.OpenAI(api_key=openai_key)
                stream = client.chat.completions.create(
                    model=openai_model,
                    messages=[
                        {
                            "role": "system",
                            "content": "Return ONLY valid JSON. Generating results in Korean.",
                        },
                        {"role": "user", "content": tuning_prompt},
                    ],
                    stream=True,
                )
            else:
                stream = openai.ChatCompletion.create(
                    model=openai_model,
                    messages=[
                        {
                            "role": "system",
                            "content": "Return ONLY valid JSON. Generating results in Korean.",
                        },
                        {"role": "user", "content": tuning_prompt},
                    ],
                    stream=True,
                )

            # Consume streaming chunks and emit per-object immediately
            for chunk in stream:
                text = extract_content(chunk)
                if not text:
                    continue

                for obj_str in feed_and_collect(text):
                    try:
                        raw_obj = json.loads(obj_str)
                    except Exception as parse_err:
                        logger.debug(
                            "Skipping malformed candidate chunk: %s", parse_err
                        )
                        continue

                    parsed_raw.append(raw_obj)

                    # Stop after 5 to align with expected count
                    if len(parsed_raw) > 5:
                        break

                    normalized = normalize_candidates(
                        parsed_raw, team=userTeam, want_count=len(parsed_raw)
                    )
                    candidate = normalized[-1]
                    candidate["userPrompt"] = userPrompt

                    safe_name = (
                        candidate.get("name")
                        or candidate.get("Nickname")
                        or "(unknown)"
                    )

                    logger.info(
                        "[Stream] candidate %d/%d: %s",
                        len(parsed_raw),
                        5,
                        safe_name,
                    )

                    yield f"data: {json.dumps(candidate, ensure_ascii=False)}\n\n"
                    # 각 후보자 전송 후 이벤트 루프에 제어권을 넘겨 즉시 flush
                    await asyncio.sleep(0)

                if len(parsed_raw) >= 5:
                    break

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.exception("Stream generation failed")
            yield 'data: {"error": "stream_generation_failed"}\n\n'

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.post("/get_news_summary")
async def get_news_summary(request: NewsSummaryRequest):
    """뉴스 요약을 받아오는 엔드포인트 (비동기 처리)

    게임 정보를 받아 뉴스 CSV를 로드하고 news_summarizer로 요약합니다.
    게임 ID 포맷: 250523_HTSS_HT_game
    - 위치 7-9: SS (어웨이팀)
    - 위치 9-11: HT (홈팀)
    """
    try:
        loop = asyncio.get_event_loop()
        # 동기 작업을 스레드풀에서 비동기로 실행
        news_data = await loop.run_in_executor(
            None, _process_news_summary_sync, request.game
        )
        return news_data

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in get_news_summary: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get news summary: {str(e)}"
        )


def _process_news_summary_sync(game: str):
    """동기적으로 뉴스 요약을 처리하는 내부 함수"""
    logger.info(f"Parsing game ID: {game}")

    date = game.split("_")[0]
    news = f"{date}recentNews"

    # 파일 경로 (backend/news/YYYYMMDD/YYYYMMDDrecentNews.csv)
    backend_dir = Path(__file__).resolve().parent
    news_csv_path = backend_dir / "news" / date / f"{news}.csv"

    # 배포 환경에서 로컬 파일이 없을 때 사용할 원격 기본 URL
    # 프런트에서 쓰는 VITE_API_URL을 우선 사용, 없으면 NEWS_REMOTE_BASE_URL, 둘 다 없으면 기본 onrender 도메인
    remote_base = (
        os.getenv("VITE_API_URL")
        or os.getenv("NEWS_REMOTE_BASE_URL")
        or "https://watchcrew-screen.onrender.com"
    ).rstrip("/")
    remote_csv_url = f"{remote_base}/news/{date}/{news}.csv"

    logger.info(f"News CSV local path: {news_csv_path}")
    logger.info(f"News CSV remote url: {remote_csv_url}")

    ndf = None

    if news_csv_path.exists():
        # 우선 로컬 파일 시도
        try:
            ndf = pd.read_csv(news_csv_path, encoding="utf-8-sig")
            logger.info(f"✅ News CSV loaded from local ({len(ndf)} rows)")
        except Exception as e:
            logger.error(f"❌ Failed to read local CSV: {e}")
            raise
    else:
        # 로컬 파일이 없으면 원격 경로 시도
        logger.warning(f"❌ Local news CSV not found, trying remote: {remote_csv_url}")
        try:
            ndf = pd.read_csv(remote_csv_url, encoding="utf-8-sig")
            logger.info(f"✅ News CSV loaded from remote ({len(ndf)} rows)")
        except Exception as e:
            logger.error(f"❌ Failed to read remote CSV: {e}")
            raise FileNotFoundError(
                f"News CSV not found locally or remotely: {news_csv_path}, {remote_csv_url}"
            ) from e

    # 팀 ID 추출 (게임 ID 포맷: 250523_HTSS_HT_game or 250523_HTSS)
    # "250523_HTSS" 형식: 위치 9-11이 away_team_id, 11-13이 home_team_id
    # "250523_HTSS_HT_game" 형식에서도 동일한 위치에서 추출 가능
    parts = game.split("_")

    if len(parts) >= 2:
        # 팀 코드 추출: "HTSS" -> away=SS, home=HT
        team_codes = parts[1]
        if len(team_codes) >= 4:
            home_team_id = team_codes[0:2]  # "HT"
            away_team_id = team_codes[2:4]  # "SS"
        else:
            logger.error(f"❌ Invalid team code format in game ID: {game}")
            raise ValueError(f"Invalid game ID format: {game}")
    else:
        logger.error(f"❌ Invalid game ID format: {game}")
        raise ValueError(f"Invalid game ID format: {game}")

    # 데이터 추출
    news_dict = {}

    # away_team_id 뉴스
    away_news_list = ndf[ndf["teamId"] == away_team_id]["title"].tolist()
    if away_team_id in TEAM_DICT:
        news_dict[TEAM_DICT[away_team_id]] = away_news_list
    else:
        logger.warning(f"Unknown team ID: {away_team_id}")

    # home_team_id 뉴스
    home_news_list = ndf[ndf["teamId"] == home_team_id]["title"].tolist()
    if home_team_id in TEAM_DICT:
        news_dict[TEAM_DICT[home_team_id]] = home_news_list
    else:
        logger.warning(f"Unknown team ID: {home_team_id}")

    logger.info(
        f"Extracted news - {away_team_id}: {len(away_news_list)} items, {home_team_id}: {len(home_news_list)} items"
    )

    news_data = news_summarizer(news_dict)
    logger.info(
        f"✅ News summary generated: {json.dumps(news_data, ensure_ascii=False)}"
    )

    return news_data


# ============================================
# Orchestrator Endpoint (from orchestration_v2.ipynb)
# ============================================


class OrchestratorRequest(BaseModel):
    """Orchestrator 요청 모델

    30초마다 자동으로 채팅 셋을 생성하며, 사용자 입력이 있으면 이를 반영합니다.
    """

    userMessages: List[Dict[str, str]] = (
        []
    )  # [{"speaker": "사용자1", "text": "메시지"}, ...]
    currGameStat: Optional[str] = "경기 진행 중"  # 현재 경기 상태 (추후 자동 업데이트)
    gameFlow: Optional[str] = ""  # 경기 흐름 요약 (추후 자동 업데이트)
    newsData: Optional[Dict[str, str]] = {}  # 뉴스 요약 데이터
    agents: List[Dict] = []  # localStorage의 ai-fan-agents


@app.post("/orchestrate")
async def orchestrate_chat(request: OrchestratorRequest):
    """에이전트들 간의 대화 스크립트를 생성하고 스트리밍으로 응답

    orchestration_v2.ipynb의 로직을 FastAPI 스트리밍으로 구현
    backend/game 폴더의 실제 게임 데이터를 사용합니다.
    """
    global current_row_index

    try:
        openai_key = os.getenv("OPENAI_API_KEY")
        openai_model = os.getenv("OPENAI_MODEL", "gpt-4.1")

        if not openai or not openai_key:
            raise HTTPException(status_code=500, detail="OpenAI API not configured")

        client = openai.OpenAI(api_key=openai_key)

        # localStorage에서 전달받은 에이전트 리스트 사용
        if request.agents and len(request.agents) > 0:
            ap_list = [
                transform_agent_for_orchestrate(agent) for agent in request.agents
            ]
            logger.info(f"Using {len(ap_list)} agents from localStorage")
        else:
            # 폴백: 하드코딩된 에이전트 사용
            ap_list = HARDCODED_AGENTS
            logger.info(f"No agents provided, using {len(ap_list)} HARDCODED_AGENTS")

        # turn_num 계산 (ipynb 로직 그대로)
        turn_num = [
            math.floor(len(ap_list) * 1 + 0.5),
            math.floor(len(ap_list) * 1.5 + 0.5),
        ]

        # context_memory 구성: 사용자 메시지를 포함
        context_memory = request.userMessages if request.userMessages else []

        # news_data 구성
        news_data = request.newsData if request.newsData else {}

        # =====================================================
        # 게임 데이터 로드 (orchestration_v2.ipynb의 Pre data, Stimulus data)
        # =====================================================
        # 현재 row_index로 게임 데이터 로드
        curr_game_stat, game_flow, df = load_game_data(row_index=current_row_index)

        # 다음 요청을 위해 row_index 증가
        if df is not None and current_row_index < len(df) - 1:
            current_row_index += 1

        logger.info(
            f"Loaded game data at row {current_row_index - 1} - currGameStat: {curr_game_stat}, gameFlow length: {len(game_flow)}"
        )

        # 프롬프트 생성 (ipynb 로직 그대로)
        prompt = f"""

당신은 야구 중계 채팅 시스템 매니저입니다. 당신의 역할은 현재 야구 경기를 시청 중인 시청자들에게, 지금 경기 상황에 맞춰 사람들이 더 재미있거나 더 유용하다고 느낄 만한 대화를 생성해 제공하는 것입니다.

주어진 데이터와 에이전트 및 페르소나 리스트 그리고 7가지 채팅 동기들을 활용하여 다음의 작업을 Chain-of-thought 방식으로 단계적으로 수행하세요.

[주어진 데이터]
# Current Game Data
- Current Game Status: The current state of the game at this moment.
- Game Flow: Summary of game events leading up to this point.

# Recent News
: 전날 업데이트된 각 팀별 최신 이슈들

# Context Memory
: 에이전트들의 이전 대화 내용들

[Agent & Personas list]
: 선택된 에이전트들과 해당 페르소나들

[Seven Chatting Motivations]
- Sharing Feelings and Thoughts
: 사람들은 경기 해석·예측을 공유하고, 반응을 보며 감정을 확인해 공감·동의/반박을 주고받기 위해 채팅한다.
- Fun and Entertainment
: 사람들은 채팅 자체가 재미있어 참여하고, 재치 있는 댓글로 웃으며 지루한 시간을 보내고 즐거움을 더하기 위해 채팅한다.
- Information Offering
: 사람들은 질문에 답하고 유용한 정보를 제공하며, 잘못된 정보를 바로잡아 전달·정정하기 위해 채팅한다.
- Information Seeking
: 사람들은 모르는 점을 질문하고 Q&A로 답을 얻으며, 규칙·팀·선수 등 필요한 정보를 배우기 위해 채팅한다.
- Emotional Release
: 사람들은 흥분·기쁨·분노를 글로 쏟아 스트레스를 풀고, 긴장 순간 감정을 더 고조시키기 위해 채팅한다.
- Intra-membership
: 팬들은 같은 팀 팬끼리 함께 응원하며 하나됨과 소속감을 느끼고, 결속을 다지며 더 열심히 응원하기 위해 채팅한다.
- Inter-membership
: 팬들은 상대 팀·팬을 견제하거나 야유하고, 우리 팀을 비판하는 상대에게 맞서 옹호하며 라이벌 의식을 드러내기 위해 채팅한다.
   
[작업]
1. Seven Chatting Motivation를 참고하여 주어진 현재 경기 데이터 상황에서 사람들이 더 재미있거나 더 유용하다고 느낄 만한 주제와 대화의 전략을 선정합니다.

2. 1에서 정해진 주제 혹은 전략에 맞춰서, 각각 다른 페르소나를 가진 에이전트들이 대화 내에서 어떤 역할을 해야하는지를 결정합니다.

3. 2.에서 결정된 역할에 맞춰 에이전트끼리 대화를 나누는 발화 텍스트를 생성합니다.

----------------

[RESPONSE RULES]
1. Output format
- 출력은 반드시 [OUTPUT FORMAT]의 JSON 구조를 따릅니다.
- agent_role과 script는 에이전트/발화의 리스트(배열)로 작성합니다.
- script는 총 {turn_num[0]} 턴 이상 {turn_num[1]} 턴 이하로 구성하세요.
- script의 각 utterance는 한 번에 한 문장을 넘지 않습니다.
- 출력시, script를 반드시 첫번째로 반환해야 합니다.

2. Rule of strategy
- strategy에는 현재 경기 데이터 상황에서 사람들이 더 재미있거나 더 유용하다고 느낄 만한 주제와 대화의 전략을 출력합니다.
- Seven Chatting Motivation 중 1 ~ 2개만 참고하여 대화 전략을 고르고, 어떤 대화를 해야할지를 결정합니다.
- 대화의 유형에는 질의 응답, 동조(긍정/부정), 갈등(같은 팀 간의/다른 팀 간의), 침묵, 환호 등이 있습니다.
- 필요한 경우, (1) 현재 경기 상황과 직접 관련이 있거나, (2) 경기가 다소 잔잔해 대화 소재가 부족한 구간이라면, 최근 팀 이슈/뉴스를 보조 주제로 활용할 수 있습니다.

3. Rule of agent_role
- agent_role에는 각 에이전트의 페르소나를 고려하여, 선택된 대화 주제 및 전략에 맞게 대화에서 수행해야 할 역할을 명시합니다.
- agent_role에 역할 설명은 반드시 해당 에이전트의 응원 team을 고려하여 작성되어야 합니다.
- 대화 주제가 최근 이슈/뉴스와 관련된 경우, agent_role은 해당 최근 이슈를 참고하여 역할을 구체화해 작성합니다.
- agent_role을 작성할 때, 각 에이전트가 다른 에이전트의 발화에 반응하거나 질문·동의·반박·보완을 수행하는 등, 상호작용 방식(예: “앞선 에이전트의 의견에 반응한다”, “상대의 질문에 답한다”, “상대의 주장에 근거를 덧붙인다”)이 드러나도록 역할을 부여합니다.
- agent_role의 개수는 선택된 에이전트의 개수에 따라 달라질 수 있습니다.

4. Rule of script
- script에는 strategy와 agent_role을 고려하여 각 에이전트가 실제 말해야하는 발화 텍스트(utterance of the speaker)을 생성합니다.
- script는 에이전트 간 상호 대화처럼 보이도록 작성합니다. 즉, 에이전트 간 대화를 서로 주고받는 흐름이 드러나야 합니다.
- 발화 순서는 정해진 역할과 에이전트의 페르소나를 고려해 결정합니다.
- 에이전트의 각 발화는 말투/톤 등은 해당 페르소나의 채팅 특성-표현 부분에 맞게 반영되어야 합니다.
- script의 대화의 문맥과 흐름은 자연스럽게 이어져야합니다.
- 에이전트의 각 발화는 문맥을 유지하면서도 해당 에이전트의 응원 team 관점이 반영되어야 합니다.
- 각 에이전트의 발화 텍스트가 서로 너무 비슷하지 않게 합니다.
- strategy 또는 agent_role이 최근 이슈/뉴스 정보를 필요로 하는 경우, 해당 최근 이슈를 참고하여 발화를 작성합니다.

----------------

[INPUT FORMAT]
# Current Game Data
- Current Game Status: {curr_game_stat}
- Game Flow: {game_flow} 

# Recent News
: {news_data}

# Context Memory
: {context_memory}

[Agent & Personas list]
: {ap_list}


[OUTPUT FORMAT]
{{
    "script": [
        {{"name": name of the speaker1, "text": utterance of the speaker1}},
        {{"name": name of the speaker2, "text": utterance of the speaker2}},
        ... ],
    "strategy": Conversation strategy for the current situation,
    "agent_role": [
        {{"name": name of agent1, "text": The role of Agent 1 in this conversation}},
        {{"name": name of agent2, "text": The role of Agent 2 in this conversation}},      
        ... ],
}}

"""

        # OpenAI API 호출 - 스트리밍 모드
        logger.info(f"Calling OpenAI with model: {openai_model}")
        request_start_time = time.time()
        response = client.chat.completions.create(
            model=openai_model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )

        # 에이전트 team 정보 매핑 (이름으로 team 찾기)
        agent_team_map = {
            agent["userName"]: agent.get("team", "samsung") for agent in ap_list
        }

        # 스트리밍 응답을 즉시 파싱하여 전송 (동기 generator로 변경하여 즉시 스트리밍)
        def generate():
            buffer = ""
            full_response = ""  # 전체 응답 저장용
            chunk_count = 0
            sent_count = 0
            script_array_found = False
            script_start_pos = -1
            sent_messages = set()  # 중복 전송 방지
            first_chunk_time = None
            script_start_time = None
            first_message_time = None
            last_message_time = None

            logger.info("Starting incremental parsing and streaming")
            orchestrate_logger.info("=" * 80)
            orchestrate_logger.info("NEW ORCHESTRATE REQUEST")
            orchestrate_logger.info("=" * 80)

            for chunk in response:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    buffer += content
                    full_response += content  # 전체 응답에도 추가
                    chunk_count += 1

                    # 첫 chunk 도착 시간 기록
                    if first_chunk_time is None:
                        first_chunk_time = time.time()
                        elapsed = first_chunk_time - request_start_time
                        logger.info(f"⏱️ First chunk received after {elapsed:.3f}s")

                    # "script": [ 배열 위치 찾기 (한 번만 실행)
                    if not script_array_found and '"script"' in buffer:
                        script_idx = buffer.find('"script"')
                        # "script" 다음의 : 와 [ 찾기
                        search_start = script_idx + len('"script"')
                        bracket_idx = buffer.find("[", search_start)
                        if bracket_idx > script_idx:
                            script_array_found = True
                            script_start_pos = bracket_idx + 1  # [ 다음 위치 저장
                            script_start_time = time.time()
                            elapsed_from_start = script_start_time - request_start_time
                            elapsed_from_first = script_start_time - first_chunk_time
                            logger.info(
                                f"⏱️ Found 'script' array at {elapsed_from_start:.3f}s (first chunk +{elapsed_from_first:.3f}s)"
                            )

                    # script 배열이 시작된 후에만 메시지 추출
                    if script_array_found and script_start_pos >= 0:
                        # script 배열의 끝(])을 찾아서 script 배열 내부만 추출
                        remaining_buffer = buffer[script_start_pos:]

                        # script 배열의 닫는 ] 찾기
                        # 중첩된 배열/객체를 고려하여 올바른 닫는 괄호 찾기
                        bracket_count = 1  # 이미 여는 [ 하나를 지나침
                        brace_count = 0
                        in_string = False
                        escape_next = False
                        script_end_pos = -1

                        for i, char in enumerate(remaining_buffer):
                            if escape_next:
                                escape_next = False
                                continue
                            if char == "\\":
                                escape_next = True
                                continue
                            if char == '"' and not escape_next:
                                in_string = not in_string
                                continue
                            if in_string:
                                continue

                            if char == "{":
                                brace_count += 1
                            elif char == "}":
                                brace_count -= 1
                            elif char == "[":
                                bracket_count += 1
                            elif char == "]":
                                bracket_count -= 1
                                if bracket_count == 0:
                                    script_end_pos = i
                                    break

                        # script 배열이 아직 완전히 도착하지 않았으면 현재까지만 파싱
                        if script_end_pos == -1:
                            script_content = remaining_buffer
                        else:
                            script_content = remaining_buffer[:script_end_pos]

                        # {"name": "...", "text": "..."} 패턴 찾기 (쉼표 선택적 포함)
                        import re

                        pattern = r'\{\s*"name"\s*:\s*"([^"]+)"\s*,\s*"text"\s*:\s*"([^"]*(?:\\.[^"]*)*)"\s*\}\s*,?'

                        matches = list(re.finditer(pattern, script_content))

                        if matches:
                            current_time = time.time()
                            for match in matches:
                                speaker = match.group(1)
                                text = match.group(2).replace(
                                    '\\"', '"'
                                )  # unescape quotes

                                # 중복 전송 방지 (같은 speaker + text 조합)
                                msg_key = f"{speaker}:{text}"
                                if msg_key in sent_messages:
                                    continue
                                sent_messages.add(msg_key)

                                team = agent_team_map.get(speaker, "samsung")

                                message = json.dumps(
                                    {"speaker": speaker, "text": text, "team": team},
                                    ensure_ascii=False,
                                )
                                sent_count += 1

                                # 타이밍 정보 계산
                                elapsed_from_start = current_time - request_start_time
                                elapsed_from_script = current_time - script_start_time

                                if first_message_time is None:
                                    first_message_time = current_time
                                    logger.info(
                                        f"⏱️ First message sent at {elapsed_from_start:.3f}s (script start +{elapsed_from_script:.3f}s)"
                                    )

                                if last_message_time is not None:
                                    time_since_last = current_time - last_message_time
                                    logger.info(
                                        f"⏱️ Message {sent_count}: speaker={speaker}, text_length={len(text)}, time_since_last={time_since_last:.3f}s"
                                    )
                                else:
                                    logger.info(
                                        f"⏱️ Message {sent_count}: speaker={speaker}, text_length={len(text)}"
                                    )

                                last_message_time = current_time
                                yield f"{message}\n"

                            # 전송한 마지막 메시지 위치까지 script_start_pos 업데이트
                            last_match = matches[-1]
                            script_start_pos += last_match.end()

            end_time = time.time()
            total_elapsed = end_time - request_start_time
            logger.info(
                f"⏱️ Streaming completed in {total_elapsed:.3f}s. Total chunks: {chunk_count}, messages sent: {sent_count}"
            )

            # 전체 응답을 orchestrate.log에 기록
            orchestrate_logger.info(f"Total elapsed time: {total_elapsed:.3f}s")
            orchestrate_logger.info(
                f"Total chunks: {chunk_count}, messages sent: {sent_count}"
            )
            orchestrate_logger.info("-" * 80)
            orchestrate_logger.info("FULL OPENAI RESPONSE:")
            orchestrate_logger.info("-" * 80)
            orchestrate_logger.info(full_response)
            orchestrate_logger.info("-" * 80)
            orchestrate_logger.info("")

            if first_chunk_time:
                logger.info(
                    f"⏱️ Timing summary: Request→FirstChunk: {(first_chunk_time - request_start_time):.3f}s"
                )
            if script_start_time:
                logger.info(
                    f"⏱️ Timing summary: Request→ScriptStart: {(script_start_time - request_start_time):.3f}s"
                )

        return StreamingResponse(generate(), media_type="application/x-ndjson")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in orchestrate: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Broadcast Data Endpoint
# ============================================


@app.post("/reset-row-index")
async def reset_row_index():
    """게임 데이터 row_index를 초기값으로 초기화합니다.

    WatchGame 화면을 벗어날 때 호출되어,
    다시 돌아오면 처음부터 데이터를 불러올 수 있도록 합니다.
    """
    global current_row_index
    current_row_index = 328  # 초기값으로 리셋
    logger.info("Reset current_row_index to 328")
    return {"status": "success", "row_index": current_row_index}


@app.get("/broadcast-data")
async def get_broadcast_data(game_id: str = "250523_HTSS") -> dict:
    """
    문자 중계 데이터를 JSON 파일에서 로드하여 반환합니다.

    Returns:
        dict: {
            "initial": List[dict] - broadcast 폴더의 초기 데이터
            "upcoming": List[dict] - tobroadcast 폴더의 추가될 데이터
        }
    """
    try:
        broadcast_path = (
            Path(__file__).resolve().parent / "broadcast" / f"{game_id}.json"
        )
        tobroadcast_path = (
            Path(__file__).resolve().parent / "tobroadcast" / f"{game_id}.json"
        )

        if not broadcast_path.exists():
            logger.warning(f"Broadcast data not found: {broadcast_path}")
            raise HTTPException(
                status_code=404, detail=f"Broadcast data not found for game {game_id}"
            )

        # broadcast 데이터 로드 (초기 상태)
        with open(broadcast_path, "r", encoding="utf-8") as f:
            initial_data = json.load(f)

        # tobroadcast 데이터 로드 (추가될 데이터)
        upcoming_data = []
        if tobroadcast_path.exists():
            with open(tobroadcast_path, "r", encoding="utf-8") as f:
                upcoming_data = json.load(f)
            logger.info(
                f"Loaded tobroadcast data from {game_id}.json ({len(upcoming_data)} rows)"
            )
        else:
            logger.info(f"No tobroadcast data found for {game_id}")

        logger.info(
            f"Loaded broadcast data from {game_id}.json (initial: {len(initial_data)}, upcoming: {len(upcoming_data)} rows)"
        )

        return {"initial": initial_data, "upcoming": upcoming_data}

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON file")
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    except Exception as e:
        logger.exception(f"Error loading broadcast data: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error loading broadcast data: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
