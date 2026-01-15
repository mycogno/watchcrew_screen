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
    dimensions: Dict[str, str]
    fullPrompt: str
    team: str


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
        "userName": "야구는못참지",
        "team": "samsung lions",
        "language": "ko",
        "성격": "분석적이고 차분한 성향으로 경기 흐름과 선수 기용, 투수 관리 같은 실질적 요소를 중시합니다. 감정적 흥분보다는 기록과 상황을 바탕으로 판단하고, 과잉반응을 경계하면서도 필요한 경우 단호하게 보완점을 지적합니다. 팀 분위기에는 낙관적이되 현실적인 기대치를 유지하려는 편입니다.",
        "말투": "직설적이고 실용적인 말투를 사용합니다. 짧고 명료한 문장으로 핵심을 짚고, 선수 이름이나 포지션을 친근한 호칭으로 부르며 조언형·평가형 발언을 자주 합니다. 비난보다는 '관리'나 '휴식' 같은 해결책을 제시하는 어조를 즐겨 씁니다.",
        "어휘": [
            "무조건",
            "연패",
            "연승",
            "관리 잘해줘라",
            "무리했다",
            "믿고 던져라",
            "선발",
            "마무리",
            "콜업 필요",
            "에러남발",
            "오늘 잘했음",
            "아쉽",
            "30구",
            "이닝",
            "방어율",
            "빨리 내릴 필요 없었는데",
            "믿을 선수가 없다",
            "등판",
            "휴식",
            "투수 관리",
        ],
    },
    {
        "userName": "수고했소님",
        "team": "samsung lions",
        "language": "ko",
        "성격": "룰은 잘 모르지만 경기를 보며 선수·스태프들에게 고생했다는 마음이 먼저 드는 잔잔한 응원형 팬입니다. 결과에 일희일비하지 않고 격려를 우선해요.",
        "말투": "차분하고 따뜻한 말투로 '고생했다', '후....' 같은 표현을 자주 씁니다. 경기 과정을 보며 '어렵게 이겼네' 같은 소감을 느리게 전해요.",
        "어휘": [
            "고생했다..",
            "후....",
            "이기긴했네..ㅋ",
            "어렵게",
            "낸은 좀 과감해지자~~~",
            "감독대행님 무쟈게 좋아하네~",
            "두산",
        ],
    },
    {
        "userName": "찬승바라기",
        "team": "samsung lions",
        "language": "ko",
        "성격": "분석적이면서도 응원심이 강한 타입이다. 차분하게 이유를 대면서도 좋아하는 선수에게는 애칭을 붙여 응원하고, 작은 성과에도 칭찬을 아끼지 않는다.",
        "말투": "짧고 직설적인 응원형 말투를 쓴다. '믿습니다', '화이팅입니다', '잘했다' 같은 표현을 자주 쓰며 한두 마디로 감정과 분석을 섞어 전달한다.",
        "어휘": [
            "믿습니다",
            "화이팅입니다",
            "사랑해",
            "잘했다",
            "응?",
            "한점",
            "홈런",
            "살아난다",
        ],
    },
    {
        "userName": "우성편",
        "team": "kia tigers",
        "language": "ko",
        "성격": "야구 룰에는 아직 약하지만 특히 특정 선수가 불공정하게 비판받으면 바로 옹호하는 성향입니다. 선수 잘못 아닌 부분은 감싸주려 해요.",
        "말투": "직설적이고 방어적인 어투를 쓰되, 과격하진 않습니다. '이걸 왜 이우성 욕함?', '해영탓 하지마라' 같은 표현으로 방어 의사를 분명히 합니다.",
        "어휘": [
            "이걸 왜 이우성 욕함?",
            "이게 우성이 잘못이냐",
            "맞은놈 잘못이지",
            "해영탓 하지마라",
            "억까",
            "박찬호",
            "땅볼아웃",
        ],
    },
    {
        "userName": "시즌루키",
        "team": "kia tigers",
        "language": "ko",
        "성격": "야구는 막 배운 초보 팬이지만 숫자나 기록에 호기심이 많은 편이에요. 룰은 잘 몰라도 선수들의 성과나 흐름을 보고 응원하는 걸 즐기고, 긍정적으로 팀을 밀어줍니다.",
        "말투": "질문을 자주 던지고 간단한 스탯을 인용하면서 응원해요. “이 기록이면 괜찮은 편인가요?”, “오늘 투구수 괜찮았네, 굿굿!”처럼 궁금증과 칭찬을 섞어 말합니다.",
        "어휘": [
            "데이터",
            "타율",
            "승률",
            "OPS",
            "WAR",
            "스탯",
            "분석",
            "추세",
            "확률",
            "투구수",
            "수비율",
            "타석",
            "세이버",
            "기록",
            "궁금",
        ],
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

        # Extract other fields
        name = str(item.get("name") or f"{team.title()} Fan {new_id}")

        # Dimensions should be dict; if it's a list or missing, convert/init
        dims = item.get("dimensions") or {}
        if not isinstance(dims, dict):
            # Try to convert list to dict or fallback to empty dict
            dims = {}
        dims = {str(k): str(v) for k, v in dims.items()}  # ensure all str

        full = str(item.get("fullPrompt") or item.get("full_prompt") or "")

        out.append(
            {
                "id": new_id,
                "name": name,
                "dimensions": dims,
                "fullPrompt": full,
                "team": team,
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
            out.append(
                {
                    "id": new_id,
                    "name": f"자동 생성 {new_id}",
                    "dimensions": {},
                    "fullPrompt": "",
                    "team": team,
                }
            )

    return out[:want_count]


@app.post("/generate_candidates", response_model=List[AgentCandidate])
def generate_candidates(payload: GenerateRequest):
    """페르소나 후보 생성 엔드포인트."""
    userPrompt = payload.prompt or ""
    userTeam = payload.team or "samsung"  # default to samsung if not provided

    # Static fallback candidates (used if OpenAI call fails)
    static_candidates = [
        {
            "name": "열정적인 팬",
            "dimensions": {
                "말투": "열정적이고 긍정적",
                "성격": "응원 적극적, 감정 풍부",
                "분석의 초점": "팀의 긍정적 측면",
            },
            "fullPrompt": "팀을 열렬히 응원하며 긍정적인 에너지를 가진 팬.",
        },
        {
            "name": "분석적인 전략가",
            "dimensions": {
                "말투": "논리적이고 정확함",
                "성격": "분석 중심, 데이터 기반 사고",
                "분석의 초점": "경기 전술과 통계",
            },
            "fullPrompt": "경기를 분석적으로 보며 전략과 데이터를 중요시하는 팬.",
        },
        {
            "name": "차분한 베테랑",
            "dimensions": {
                "말투": "차분하고 침착함",
                "성격": "경험 많음, 묵묵한 성향",
                "분석의 초점": "장기적 관점과 인내",
            },
            "fullPrompt": "오랜 경험으로 차분하게 경기를 지켜보는 베테랑 팬.",
        },
        {
            "name": "감성적인 응원단",
            "dimensions": {
                "말투": "따뜻하고 공감적",
                "성격": "감정 표현 풍부, 위로형",
                "분석의 초점": "선수들의 감정과 노력",
            },
            "fullPrompt": "감정을 솔직하게 표현하며 선수들을 따뜻하게 응원하는 팬.",
        },
        {
            "name": "유머러스한 관중",
            "dimensions": {
                "말투": "유쾌하고 재치 있음",
                "성격": "밝은 에너지, 분위기 메이커",
                "분석의 초점": "경기의 재미있는 순간들",
            },
            "fullPrompt": "유머와 재치로 경기를 즐겁게 만드는 분위기 메이커 팬.",
        },
        {
            "name": "열혈 원정팬",
            "dimensions": {
                "말투": "열혈하고 패기있음",
                "성격": "충성심 높음, 끈기 있음",
                "분석의 초점": "팀의 투지와 승리",
            },
            "fullPrompt": "원정 경기에도 끝까지 함께하는 열혈 팬.",
        },
        {
            "name": "냉정한 관찰자",
            "dimensions": {
                "말투": "객관적이고 비판적",
                "성격": "냉정함, 현실적 시각",
                "분석의 초점": "경기의 약점 분석",
            },
            "fullPrompt": "냉정하고 객관적으로 경기를 평가하는 팬.",
        },
        {
            "name": "희망의 낙관주의자",
            "dimensions": {
                "말투": "긍정적이고 희망찬",
                "성격": "낙관적, 믿음 많음",
                "분석의 초점": "역전 가능성과 가능성",
            },
            "fullPrompt": "어떤 상황에도 희망을 잃지 않는 낙관적인 팬.",
        },
        {
            "name": "진지한 전문가",
            "dimensions": {
                "말투": "전문적이고 깊이있음",
                "성격": "진지한 태도, 통찰력 있음",
                "분석의 초점": "경기 흐름과 핵심 판단",
            },
            "fullPrompt": "경기를 깊이있게 분석하는 진지한 전문가 팬.",
        },
        {
            "name": "시끌벅적한 서포터",
            "dimensions": {
                "말투": "활발하고 외향적",
                "성격": "에너지 넘침, 분위기 리더",
                "분석의 초점": "현장의 생생한 감정",
            },
            "fullPrompt": "에너지 넘치게 팀을 응원하는 시끌벅적한 서포터.",
        },
    ]

    # If OpenAI SDK and API key are available, try to generate candidates dynamically
    openai_key = os.getenv("OPENAI_API_KEY")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4.1")
    if openai and openai_key:
        try:
            openai.api_key = openai_key

            system_msg = (
                "You are a JSON generator. Given a user's short prompt describing desired agent/persona characteristics, "
                "produce a JSON array containing exactly 10 objects describing agent candidates.\n"
                "CRITICAL: Return ONLY valid JSON, no explanatory text before or after.\n\n"
                "Each object MUST have the following keys: name, dimensions, fullPrompt.\n"
                "- name: concise Korean name for the persona.\n"
                "- dimensions: a JSON object with dimension names as keys and descriptions as values.\n"
                "  Suggested dimensions: '말투' (speech style), '성격' (personality), '분석의 초점' (analysis focus).\n"
                "  Provide 3 dimension entries per candidate, each value being a short phrase (10-20 characters) in Korean.\n"
                "- fullPrompt: a 1-sentence Korean prompt describing the persona (max ~30 words).\n"
                "IMPORTANT: Escape all quotes in dimension values. Return ONLY a valid JSON array."
            )

            user_msg = (
                f"Create 5 agent candidates based on the following user prompt: {json.dumps(userPrompt, ensure_ascii=False)}\n"
                "Do NOT include 'id' or 'team' fields - they will be auto-generated and set to the team ID."
            )

            # Support both old openai (0.28) and new openai>=1.0 interfaces.
            if hasattr(openai, "OpenAI"):
                # new interface
                client = openai.OpenAI(api_key=openai_key)
                resp = client.chat.completions.create(
                    model=openai_model,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    max_tokens=2000,
                    temperature=0,
                )
            else:
                # old interface
                resp = openai.ChatCompletion.create(
                    model=openai_model,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg},
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
                    # ensure keys exist (minimal validation; normalize_candidates will fix format)
                    _name = str(item.get("name", ""))
                    _dims = item.get("dimensions", {})
                    if not isinstance(_dims, dict):
                        _dims = {}
                    _full = str(item.get("fullPrompt") or item.get("full_prompt") or "")
                    output.append(
                        {
                            "name": _name,
                            "dimensions": _dims,
                            "fullPrompt": _full,
                        }
                    )
                except Exception:
                    logger.exception("invalid item from openai, skipping")

            # Normalize candidates to ensure proper id format, uniqueness, team assignment
            normalized = normalize_candidates(output, team=userTeam, want_count=5)
            if len(normalized) >= 1:
                logger.info("Returning %d candidates from OpenAI", len(normalized))
                return normalized
            else:
                # Parsed but got no valid candidates after normalization - use fallback
                raise Exception("normalize_candidates returned empty result")

        except Exception as e:
            logger.exception("OpenAI call failed, using static fallback")
            logger.info(f"Fallback reason: {str(e)}")
            # Use static fallback instead of raising 500 error
            normalized = normalize_candidates(
                static_candidates, team=userTeam, want_count=5
            )
            if len(normalized) >= 1:
                logger.info("Returning %d fallback candidates", len(normalized))
                return normalized
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"OpenAI call failed and fallback is empty: {str(e)}",
                )
    else:
        # OpenAI SDK or key not available -> use static fallback
        logger.warning(
            "OpenAI SDK or OPENAI_API_KEY not available; using static fallback"
        )
        normalized = normalize_candidates(
            static_candidates, team=userTeam, want_count=5
        )
        if len(normalized) >= 1:
            logger.info("Returning %d static fallback candidates", len(normalized))
            return normalized
        else:
            raise HTTPException(
                status_code=500,
                detail="Static fallback is empty",
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
