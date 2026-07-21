"""
Edmond 的 portfolio 网站助理 —— Flask 后端

职责:
  1. 提供网页 (GET /)
  2. 提供聊天接口 (POST /chat)，维护每个访客各自的多轮对话历史
  3. 提供重置接口 (POST /reset)

安全要点: DEEPSEEK_API_KEY 只在这个文件里读取，永远不会出现在前端。
前端只跟这个后端说话，不直接调 DeepSeek。
"""

import os
import secrets

import anthropic
from flask import Flask, jsonify, render_template, request, session
from flask_cors import CORS

# ---------------------------------------------------------------------------
# 1. 客户端初始化（照抄已跑通的调用方式，base_url / model 不改）
# ---------------------------------------------------------------------------
client = anthropic.Anthropic(
    api_key=os.environ["DEEPSEEK_API_KEY"],  # ← 读环境变量名，不是 key 本身
    base_url="https://api.deepseek.com/anthropic",
)

MODEL = "deepseek-v4-flash"  # flash 就够，不用 pro
MAX_TOKENS = 1024

# 每个访客最多保留最近 12 条消息 = 6 轮问答。
# 两个原因：(1) 控制成本 —— 历史越长，每次调用的 input tokens 越多；
#          (2) Flask 的 session 存在浏览器 cookie 里，有 4KB 上限，历史不截断会撑爆。
MAX_MESSAGES = 12

# 单条消息长度上限，防止有人贴一整本书进来烧 token
MAX_INPUT_CHARS = 1000

# ---------------------------------------------------------------------------
# 2. Bot 人设 —— resume 内容 + 行为规则，全部写死在后端
# ---------------------------------------------------------------------------
with open("system_prompt.txt", "r", encoding="utf-8") as _f:
    SYSTEM_PROMPT = _f.read()

# ---------------------------------------------------------------------------
# 3. Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)

# 跨域配置：只对聊天接口开放，允许之后部署在 GitHub Pages 的前端调用。
# supports_credentials=True —— 对话历史存在 session cookie 里，跨域要带 cookie 必须开这个。
CORS(
    app,
    resources={r"/chat": {"origins": "https://edmond1473.github.io"},
               r"/reset": {"origins": "https://edmond1473.github.io"}},
    supports_credentials=True,
)

# session 需要一个密钥来给 cookie 签名（防止访客篡改自己的对话历史）。
# 生产环境请设置 FLASK_SECRET_KEY 环境变量；
# 没设的话这里临时生成一个 —— 但每次重启服务，所有人的对话历史都会失效。
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)


@app.route("/")
def index():
    """返回聊天页面。"""
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    """
    接收前端的一条用户消息 → 带上该访客的历史调用模型 → 返回回复。

    历史存在 session 里，所以每个浏览器有自己独立的对话，访客之间不会串台。
    """
    data = request.get_json(silent=True) or {}
    user_input = (data.get("message") or "").strip()

    # --- 输入校验 ---
    if not user_input:
        return jsonify({"error": "消息不能为空"}), 400
    if len(user_input) > MAX_INPUT_CHARS:
        return jsonify({"error": f"消息太长了（上限 {MAX_INPUT_CHARS} 字）"}), 400

    # --- 取出这个访客的历史（没有就是空的）---
    messages = session.get("messages", [])

    # 1. 用户这句进历史
    messages.append({"role": "user", "content": user_input})

    # 2. 截断：只留最近 MAX_MESSAGES 条。
    #    截完要确保第一条是 user —— 历史以 assistant 开头的话 API 会报错。
    if len(messages) > MAX_MESSAGES:
        messages = messages[-MAX_MESSAGES:]
        if messages[0]["role"] == "assistant":
            messages = messages[1:]

    # 3. 把【整个历史】发出去 —— 这就是模型"记得"前面聊过什么的原因
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
    except Exception as e:
        # 后端打印真实错误方便你排查，但只给前端一句友善的提示（别把内部细节漏出去）
        print(f"[API 出错] {type(e).__name__}: {e}")
        return jsonify({"error": "抱歉，我这边出了点问题，请稍后再试。"}), 502

    # 4. content 是个 list，可能含 thinking block —— 只取文字块
    reply = "".join(b.text for b in response.content if b.type == "text")

    # 5. AI 的回复也要进历史 —— 漏了这步 bot 下一轮就失忆了
    messages.append({"role": "assistant", "content": reply})
    session["messages"] = messages

    # 6. token 用量只 print 在后端终端，前端不显示（访客看到会很怪）
    print(
        f"[{len(messages)//2} 轮] 输入 {response.usage.input_tokens} tokens "
        f"| 输出 {response.usage.output_tokens} tokens"
    )

    return jsonify({"reply": reply})


@app.route("/reset", methods=["POST"])
def reset():
    """清空当前访客的对话历史（前端"新对话"按钮调这个）。"""
    session.pop("messages", None)
    print("[会话已重置]")
    return jsonify({"ok": True})


if __name__ == "__main__":
    # 不用 5000 —— macOS 的 AirPlay Receiver 会占用它，请求会被 AirPlay 抢走返回 403
    app.run(debug=True, port=5001)
