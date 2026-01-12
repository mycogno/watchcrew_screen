from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Literal, Dict
from fastapi.middleware.cors import CORSMiddleware
import os
import json
import logging
from dotenv import load_dotenv
from pathlib import Path

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
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("watchcrew.backend")

# log whether OPENAI_API_KEY is present (do not log the key itself)
logger.info("OPENAI_API_KEY present: %s", bool(os.getenv("OPENAI_API_KEY")))

# 환경변수로 허용할 origin을 설정할 수 있도록 함 (쉼표로 구분)
_allowed = os.getenv(
    "BACKEND_ALLOWED_ORIGINS",
    "http://localhost:8080,http://localhost:3000,https://watchcrewscreenhai.vercel.app/,https://watchcrewscreenhai.vercel.app",
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


def normalize_candidates(
    parsed: List[dict], team: str = "samsung", want_count: int = 10
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
                f"Create 10 agent candidates based on the following user prompt: {json.dumps(userPrompt, ensure_ascii=False)}\n"
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
                    temperature=0.7,
                    max_tokens=2000,
                )
            else:
                # old interface
                resp = openai.ChatCompletion.create(
                    model=openai_model,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.7,
                    max_tokens=2000,
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
            normalized = normalize_candidates(output, team=userTeam, want_count=10)
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
                static_candidates, team=userTeam, want_count=10
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
            static_candidates, team=userTeam, want_count=10
        )
        if len(normalized) >= 1:
            logger.info("Returning %d static fallback candidates", len(normalized))
            return normalized
        else:
            raise HTTPException(
                status_code=500,
                detail="Static fallback is empty",
            )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
