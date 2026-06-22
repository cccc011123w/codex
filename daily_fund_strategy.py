import datetime as dt
import email.message
import json
import os
import re
import smtplib
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "holdings.json"


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def http_get(url: str, timeout: int = 12) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 fund-strategy-bot",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def http_post_json(url: str, payload: dict, headers: dict, timeout: int = 60) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc


def fetch_fund_estimate(code: str) -> dict:
    if not code:
        return {"status": "missing_code"}

    url = f"https://fundgz.1234567.com.cn/js/{urllib.parse.quote(code)}.js?rt={int(dt.datetime.now().timestamp())}"
    raw = http_get(url)
    match = re.search(r"jsonpgz\((.*)\);?", raw)
    if not match:
        return {"status": "unavailable", "raw": raw[:200]}
    data = json.loads(match.group(1))
    return {
        "status": "ok",
        "code": data.get("fundcode", code),
        "name": data.get("name"),
        "net_value_date": data.get("jzrq"),
        "net_value": data.get("dwjz"),
        "estimated_value": data.get("gsz"),
        "estimated_change_pct": data.get("gszzl"),
        "estimate_time": data.get("gztime"),
    }


def fetch_index_snapshot() -> dict:
    symbols = {
        "上证指数": "1.000001",
        "深证成指": "0.399001",
        "创业板指": "0.399006",
        "沪深300": "1.000300",
        "中证500": "1.000905",
        "恒生指数": "100.HSI",
        "纳斯达克": "105.NDX",
        "黄金": "113.GC00Y",
    }
    secids = ",".join(symbols.values())
    url = (
        "https://push2.eastmoney.com/api/qt/ulist.np/get?"
        + urllib.parse.urlencode(
            {
                "fltt": "2",
                "fields": "f12,f14,f2,f3,f4,f6",
                "secids": secids,
            }
        )
    )
    try:
        data = json.loads(http_get(url))
        rows = data.get("data", {}).get("diff", []) or []
        return {
            row.get("f14") or row.get("f12"): {
                "price": row.get("f2"),
                "change_pct": row.get("f3"),
                "change": row.get("f4"),
                "turnover": row.get("f6"),
            }
            for row in rows
        }
    except Exception as exc:
        return {"error": str(exc)}


def build_prompt(config: dict, fund_data: list[dict], market_data: dict) -> str:
    today = dt.datetime.utcnow() + dt.timedelta(hours=8)
    return f"""
你是谨慎、可执行导向的中文基金交易策略助手。今天北京时间日期：{today:%Y-%m-%d %H:%M}。

请基于以下用户持仓、基金估值/净值数据、市场指数快照，生成一份适合手机阅读的基金交易策略邮件。

用户持仓基准：
{json.dumps(config["holdings"], ensure_ascii=False, indent=2)}

基金最新同步数据：
{json.dumps(fund_data, ensure_ascii=False, indent=2)}

市场指数快照：
{json.dumps(market_data, ensure_ascii=False, indent=2)}

输出要求：
1. 开头用 5 行以内给出“今日总决策”：持有、加仓、减仓、止盈、观望。
2. 逐只基金列出：最新涨跌/估值变化、相对用户截图基准的风险变化、今日动作、触发条件、建议仓位区间。
3. 明确哪些持仓已有较高浮盈，是否要分批止盈或设置回撤线。
4. 给出适合新建仓的方向，按优先级排序，说明建仓节奏和不买条件。
5. 若今天可能不是交易日或数据缺失，明确标注，不要假装知道。
6. 语言要简洁、可执行，避免空泛。
7. 结尾声明：这不是个性化投资顾问意见，交易风险由用户自行承担。
"""


def call_openai(prompt: str) -> str:
    api_key = require_env("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL", "gpt-5.5").strip() or "gpt-5.5"
    response = http_post_json(
        "https://api.openai.com/v1/responses",
        {
            "model": model,
            "input": prompt,
        },
        {"Authorization": f"Bearer {api_key}"},
    )

    text_parts = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                text_parts.append(content.get("text", ""))
    if text_parts:
        return "\n".join(text_parts).strip()

    if response.get("output_text"):
        return str(response["output_text"]).strip()

    raise RuntimeError(f"Could not parse OpenAI response: {json.dumps(response, ensure_ascii=False)[:1000]}")


def send_email(subject: str, body: str) -> None:
    sender = require_env("QQMAIL_USER")
    recipient = os.environ.get("QQMAIL_TO", "").strip() or "1678221404@qq.com"
    auth_code = require_env("QQMAIL_AUTH_CODE")

    message = email.message.EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body, subtype="plain", charset="utf-8")

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.qq.com", 465, context=context, timeout=30) as smtp:
        smtp.login(sender, auth_code)
        smtp.send_message(message)


def main() -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    fund_data = []
    for holding in config["holdings"]:
        item = {"holding": holding}
        try:
            item["data"] = fetch_fund_estimate(holding.get("code", ""))
        except Exception as exc:
            item["data"] = {"status": "error", "error": str(exc)}
        fund_data.append(item)

    market_data = fetch_index_snapshot()
    prompt = build_prompt(config, fund_data, market_data)
    strategy = call_openai(prompt)

    today = dt.datetime.utcnow() + dt.timedelta(hours=8)
    subject = f"基金交易策略 - {today:%Y-%m-%d}"
    send_email(subject, strategy)
    print(f"Sent strategy email: {subject}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
