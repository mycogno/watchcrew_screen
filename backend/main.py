from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
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


class GenerateRequest(BaseModel):
    prompt: str = ""
    team: str = ""


class AgentCandidate(BaseModel):
    id: str
    name: str
    team: str
    userPrompt: str = ""  # 사용자 입력 프롬프트
    팬의특성: Dict[str, str] = {}
    애착: Dict[str, str] = {}
    채팅특성: Dict[str, str] = {}
    표현: Dict[str, str] = {}
    채팅특성요약: str = ""  # 채팅 특성 요약
    표현요약: str = ""  # 표현 요약


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
- 각 팀 요약은 2~5문장으로 작성하고, 문장마다 다른 핵심 포인트를 담는다.
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
        response = client.chat.completions.create(
            model=openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )

        chatResult = response.choices[0].message.content
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
    try:
        game_path = Path(__file__).resolve().parent / "game" / game_file

        if not game_path.exists():
            logger.warning(f"Game file not found: {game_path}, using default data")
            return "경기 진행 중", "경기 흐름 데이터 없음", None

        # CSV 파일 로드
        df = pd.read_csv(game_path, encoding="utf-8-sig")

        if df.empty:
            logger.warning(f"Game data is empty: {game_path}")
            return "경기 진행 중", "경기 흐름 데이터 없음", df

        # 중복 제거 (orchestration_v2.ipynb 참고)
        df = df.drop_duplicates("messageTime").reset_index(drop=True)

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

        logger.info(f"Loaded game data from {game_file} at row {row_index}")
        logger.debug(f"Current game stat: {curr_game_stat}")
        logger.debug(f"Game flow: {game_flow[:100]}...")  # 첫 100자만 로그

        return curr_game_stat, game_flow, df

    except Exception as e:
        logger.exception(f"Error loading game data: {e}")
        return "경기 진행 중", "경기 흐름 데이터 없음", None


# ============================================
# Agent Candidate normalization
# ============================================


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

        # Extract name (or Nickname or userName for backward compatibility)
        user_name = str(
            item.get("name")
            or item.get("userName")
            or item.get("Nickname")
            or f"{team.title()}Fan{counter}"
        )

        # Extract nested attributes - ensure they are dicts
        fan_traits = item.get("팬의 특성") or item.get("팬의특성") or {}
        if not isinstance(fan_traits, dict):
            fan_traits = {}

        attachment = item.get("애착") or {}
        if not isinstance(attachment, dict):
            attachment = {}

        raw_chat_traits = item.get("채팅 특성") or item.get("채팅특성") or {}
        if not isinstance(raw_chat_traits, dict):
            raw_chat_traits = {}

        # New nested schema: 채팅 특성 내부에 "내용", "채팅 내용 요약", "표현", "채팅 표현 요약" 포함
        chat_content = (
            raw_chat_traits.get("내용")
            if isinstance(raw_chat_traits.get("내용"), dict)
            else {}
        )
        expression = (
            raw_chat_traits.get("표현")
            if isinstance(raw_chat_traits.get("표현"), dict)
            else {}
        )

        # Extract summaries (string)
        chat_summary = (
            raw_chat_traits.get("채팅 내용 요약")
            or raw_chat_traits.get("채팅특성요약")
            or item.get("채팅 특성 요약")
            or item.get("채팅특성요약")
            or ""
        )
        expression_summary = (
            raw_chat_traits.get("채팅 표현 요약")
            or raw_chat_traits.get("채팅표현요약")
            or item.get("표현 요약")
            or item.get("표현요약")
            or ""
        )

        out.append(
            {
                "id": new_id,
                "name": user_name,
                "team": team,
                "userPrompt": "",  # Will be set by the caller
                "팬의특성": fan_traits,
                "애착": attachment,
                "채팅특성": chat_content,
                "표현": expression,
                "채팅특성요약": chat_summary,
                "표현요약": expression_summary,
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
                    "팬의특성": {},
                    "애착": {},
                    "채팅특성": {},
                    "표현": {},
                    "채팅특성요약": "",
                    "표현요약": "",
                }
            )

    return out[:want_count]


def make_tuning_prompt(
    user_team: str, persona_db: List[dict], user_request: str
) -> str:
    return f"""
당신은 사용자의 요구사항을 기반으로 야구 팬 페르소나를 커스터마이징하는 페르소나 제작자(Persona Generator)입니다. 
당신의 역할은 페르소나 데이터베이스 내에서 사용자의 요구사항과 유사한 페르소나를 검색한 후, 해당 페르소나를 사용자의 요구사항에 맞게 커스터마이징하는 것 입니다.

또한 당신은 온라인 커뮤니케이션 환경에서의 가명성(pseudonymity)을 고려하여, 각 페르소나의 정체성을 압축적으로 드러내는 닉네임(name)을 생성해야 합니다.
이 닉네임은 완전한 익명성이 아닌, 팀 소속감·팬 성향·행동 스타일을 암시하는 ‘약한 정체성 단서(cue to identity)’로 기능해야 합니다.

[작업]
1. 페르소나 데이터베이스 내에서 사용자의 요구사항과 유사한 페르소나 최대 3개를 선택하세요.
2. 선택한 페르소나를 바탕으로 사용자의 요구사항에 맞게 커스터마이징하여 새로운 사용자 맞춤형 야구 팬 페르소나 5개를 생성하세요.
3. 각 페르소나마다 하나의 닉네임(name) Attribute를 생성하세요.

[닉네임 생성 규칙]
- 닉네임은 실명이 아닌 가명(pseudonym)이어야 합니다.
- 닉네임은 다음 요소 중 2개 이상을 암시적으로 반영해야 합니다:
  · 사용자의 선호 야구 팀
  · 팬의 행동 성향(예: 열성, 분석형, 직관형, 커뮤니티 중심형 등)
  · 응원 방식 또는 팬 문화(직관, 기록 분석, 굿즈, 온라인 활동 등)
- 닉네임은 과도한 개인 식별 정보(연도, 실명 추정 정보 등)를 포함하지 마세요.
- 5개의 페르소나 간 닉네임은 서로 중복되지 않아야 합니다.
- 닉네임과 해당 페르소나의 다른 Attribute-Value들은 의미적으로 일관되어야 합니다.

[주어진 데이터 설명]
# 사용자 선호 야구 팀
: 사용자가 응원하고 좋아하는 야구 팀 이름

# 페르소나 데이터베이스
: 100개의 다양한 야구 팬 페르소나로 이루어진 리스트이며,
  각각의 페르소나는 Dictionary 형태의 Attribute-Example Value 구조를 가짐

# 사용자 요구사항
: 사용자가 원하는 페르소나 특성

----------------

[RESPONSE RULES]
- 출력은 반드시 [OUTPUT FORMAT]에서 정의한 구조를 따릅니다.
- 전체 출력은 하나의 리스트(list)이며, 그 안에 총 5개의 JSON 형태 페르소나가 포함되어야 합니다.
- 각 페르소나는 기존 데이터베이스에서 선택된 페르소나의 Attribute를 key로 갖는 dictionary 형태여야 합니다.
- 기존 데이터베이스에 존재하지 않는 디멘션은 임의로 추가·수정·생성하지 마세요.
  (단, name Attribute는 예외적으로 반드시 포함해야 합니다.)
- 각 Attribute에 대응하는 Value는 반드시 사용자의 요구사항을 반영해야 합니다.
- 하나의 페르소나 내 모든 Attribute-Value 조합은 의미적으로 모순되지 않아야 합니다.
- 5개의 페르소나는 모두 사용자의 요구사항을 반영하되,
  Example Value의 중복을 최소화하세요.
- 어떠한 경우에도 영문이 포함되어서는 안됩니다. 모든 내용을 한국어로 번역하세요.

----------------

[INPUT FORMAT]
# 사용자 선호 야구 팀
: {user_team}

# 페르소나 데이터베이스
: {persona_db}

# 사용자 요구사항
: {user_request}

[OUTPUT FORMAT]
[
  {{
    "name": "string",
    "팬의 특성": {{ ... }},
    "애착": {{ ... }},
    "채팅 특성": {{
      "내용": {{
        "Attribution of Responsibility": "string",
        "Target of Evaluation": "string",
        "Evaluative Focus (Outcome vs Process)": "string",
        "Use of Numerical/Technical Signals": "string"
      }},
      "채팅 내용 요약": "string",
      "표현": {{
        "Tone and Linguistic Style": "string",
        "Temporal Reactivity": "string",
        "Collective Action Calls": "string",
        "Polarity toward Same Target": "string"
      }},
      "채팅 표현 요약": "string"
    }}
  }},
  ...
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

        # system_msg = (
        #     "You are a JSON generator. Given a user's short prompt describing desired agent/persona characteristics, "
        #     "produce a JSON array containing exactly 10 objects describing agent candidates.\n"
        #     "CRITICAL: Return ONLY valid JSON, no explanatory text before or after.\n\n"
        #     "Each object MUST have the following keys: name, dimensions, fullPrompt.\n"
        #     "- name: concise Korean name for the persona.\n"
        #     "- dimensions: a JSON object with dimension names as keys and descriptions as values.\n"
        #     "  Suggested dimensions: '말투' (speech style), '성격' (personality), '분석의 초점' (analysis focus).\n"
        #     "  Provide 3 dimension entries per candidate, each value being a short phrase (10-20 characters) in Korean.\n"
        #     "- fullPrompt: a 1-sentence Korean prompt describing the persona (max ~30 words).\n"
        #     "IMPORTANT: Escape all quotes in dimension values. Return ONLY a valid JSON array."
        # )

        # user_msg = (
        #     f"Create 5 agent candidates based on the following user prompt: {json.dumps(userPrompt, ensure_ascii=False)}\n"
        #     "Do NOT include 'id' or 'team' fields - they will be auto-generated and set to the team ID."
        # )

        # Load persona pool from backend directory
        persona_pool_path = Path(__file__).resolve().parent / "persona_pool.json"
        with open(persona_pool_path, "r", encoding="utf-8") as f:
            persona_pool = json.load(f)

        # Support both old openai (0.28) and new openai>=1.0 interfaces.
        if hasattr(openai, "OpenAI"):
            # new interface
            client = openai.OpenAI(api_key=openai_key)
            tuning_prompt = make_tuning_prompt(
                user_team=userTeam, persona_db=persona_pool, user_request=userPrompt
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
                max_tokens=2000,
                temperature=0,
            )
        else:
            # old interface
            tuning_prompt = make_tuning_prompt(
                user_team=userTeam, persona_db=persona_pool, user_request=userPrompt
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
                max_tokens=2000,
                temperature=0,
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

                    try:
                        parsed = json.loads(json_str)
                        logger.info("Successfully parsed JSON after fixes")
                    except Exception as e3:
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

        # 하드코딩된 에이전트 리스트 사용 (추후 AgentCreator에서 받도록 수정 예정)
        ap_list = HARDCODED_AGENTS

        # turn_num 계산 (ipynb 로직 그대로)
        turn_num = [
            math.floor(len(ap_list) * 1 + 0.5),
            math.floor(len(ap_list) * 1.5 + 0.5),
        ]

        # context_memory 구성: 사용자 메시지를 포함
        context_memory = request.userMessages if request.userMessages else []

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

        # Five Chatting Motivations
        five_motivations = """
[Five Chatting Motivations]
- Sharing Feelings and Thoughts
: 사람들은 무언가가 일어날 때 다른 사람들의 반응을 보고, 실시간으로 생각과 감정을 나누기 위해 채팅한다.
- Membership
: 사람들은 다른 팬들과 함께 응원하며 하나됨을 느끼고, 충성심을 보여주기 위해 우리 팀을 옹호하려고 채팅한다.
- Information Sharing
: 사람들은 질문하고 답을 얻으며, 경기 규칙이나 선수 별명 같은 유용한 정보를 배우기 위해 채팅한다.
- Fun and Entertainment
: 사람들은 경기가 지루할 때 시간을 보내고, 다른 사람들의 댓글을 읽는 게 재미있어서 채팅한다.
- Emotional Release
: 사람들은 떠오르는 생각을 쓰고 감정을 표현하며, 강한 순간에는 채팅으로 소리치듯 반응하기 위해 채팅한다.
"""

        # 프롬프트 생성 (ipynb 로직 그대로)
        prompt = f"""
당신은 야구 중계 채팅 시스템 매니저입니다. 당신의 역할은 현재 야구 경기를 시청 중인 시청자들에게, 지금 경기 상황에 맞춰 사람들이 더 재미있거나 더 유용하다고 느낄 만한 대화를 생성해 제공하는 것입니다.

주어진 데이터와 에이전트 및 페르소나 리스트 그리고 5가지 채팅 동기들을 활용하여 다음의 작업을 Chain-of-thought 방식으로 단계적으로 수행하세요.

[주어진 데이터]
# Current Game Data
- Current Game Status: The current state of the game at this moment.
- Game Flow: Summary of game events leading up to this point.

# Context Memory
: 에이전트들의 이전 대화 내용들

[Agent & Personas list]
: 선택된 에이전트들과 해당 페르소나들

{five_motivations}
 
[작업]
1. Five Chatting Motivation를 참고하여 주어진 현재 경기 데이터 상황에서 사람들이 더 재미있거나 더 유용하다고 느낄 만한 주제와 대화의 전략을 선정합니다.

2. 1에서 정해진 주제 혹은 전략에 맞춰서, 각각 다른 페르소나를 가진 에이전트들이 대화 내에서 어떤 역할을 해야하는지를 결정합니다.

3. 2.에서 결정된 역할에 맞춰 에이전트끼리 대화를 나누는 발화 텍스트를 생성합니다.

----------------

[RESPONSE RULES]
1. Output format
- 출력은 반드시 [OUTPUT FORMAT]의 JSON 구조를 따릅니다.
- agent_role과 script는 에이전트/발화의 리스트(배열)로 작성합니다.
- script는 총 {turn_num[0]} 턴 이상 {turn_num[1]} 턴 이하로 구성하세요.
- script의 각 utterance는 한 번에 한 문장을 넘지 않습니다.

2. Rule of strategy
- strategy에는 현재 경기 데이터 상황에서 사람들이 더 재미있거나 더 유용하다고 느낄 만한 주제와 대화의 전략을 출력합니다.
- Five Chatting Motivation 중 1개만 참고하여 대화 전략을 고르고, 어떤 대화를 해야할지를 결정합니다.
- 대화의 유형에는 질의 응답, 동조(긍정/부정), 갈등(같은 팀 간의/다른 팀 간의), 침묵, 환호 등이 있습니다.

3. Rule of agent_role
- agent_role에는 각 에이전트의 페르소나를 고려하여, 선택된 대화 주제 및 전략에 맞게 대화에서 수행해야 할 역할을 명시합니다.
- agent_role에 역할 설명은 반드시 해당 에이전트의 응원 team을 고려하여 작성되어야 합니다.
- agent_role을 작성할 때, 각 에이전트가 다른 에이전트의 발화에 반응하거나 질문·동의·반박·보완을 수행하는 등, 상호작용 방식(예: "앞선 에이전트의 의견에 반응한다", "상대의 질문에 답한다", "상대의 주장에 근거를 덧붙인다")이 드러나도록 역할을 부여합니다.
- agent_role의 개수는 선택된 에이전트의 개수에 따라 달라질 수 있습니다.

4. Rule of script
- script에는 strategy와 agent_role을 고려하여 각 에이전트가 실제 말해야하는 발화 텍스트(utterance of the speaker)을 생성합니다.
- script는 에이전트 간 상호 대화처럼 보이도록 작성합니다. 즉, 에이전트 간 대화를 서로 주고받는 흐름이 드러나야 합니다.
- 발화 순서는 정해진 역할과 에이전트의 페르소나를 고려해 결정합니다.
- 에이전트의 각 발화는 말투/톤 등은 해당 페르소나에 맞게 반영되어야 합니다.
- script의 대화의 문맥과 흐름은 자연스럽게 이어져야합니다.
- 에이전트의 각 발화는 문맥을 유지하면서도 해당 에이전트의 응원 team 관점이 반영되어야 합니다.
- 각 에이전트의 발화 텍스트가 서로 너무 비슷하지 않게 합니다.

----------------

[INPUT FORMAT]
# Current Game Data
- Current Game Status: {curr_game_stat}
- Game Flow: {game_flow} 

# Context Memory
: {context_memory}

[Agent & Personas list]
: {ap_list}


[OUTPUT FORMAT]
{{
    "strategy": Conversation strategy for the current situation,
    "agent_role": [
        {{"name": name of agent1, "text": The role of Agent 1 in this conversation}},
        {{"name": name of agent2, "text": The role of Agent 2 in this conversation}},      
        ... ],
    "script": [
        {{"name": name of the speaker1, "text": utterance of the speaker1}},
        {{"name": name of the speaker2, "text": utterance of the speaker2}},
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
            temperature=0,
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
                        # script 배열 내용만 추출 (버퍼 전체가 아닌 script 시작 위치 이후만)
                        script_content = buffer[script_start_pos:]

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
            if first_message_time:
                logger.info(
                    f"⏱️ Timing summary: Request→FirstMessage: {(first_message_time - request_start_time):.3f}s"
                )
            if last_message_time:
                logger.info(
                    f"⏱️ Timing summary: Request→LastMessage: {(last_message_time - request_start_time):.3f}s"
                )

        return StreamingResponse(generate(), media_type="application/x-ndjson")

    except json.JSONDecodeError as e:
        logger.exception(f"JSON parsing error in orchestrate: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to parse response: {str(e)}"
        )
    except Exception as e:
        logger.exception(f"Error in orchestrate: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
