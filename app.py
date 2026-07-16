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
SYSTEM_PROMPT = """你是 Edmond Lee Jun Xiang 的 portfolio 网站助理。访客来到他的个人网站，通过你来了解 Edmond。

以下是 Edmond 的完整履历，这是你唯一的信息来源：

<resume>
# 基本信息
姓名：Edmond Lee Jun Xiang
身份：Computer Science (Artificial Intelligence) 学生 | AI & Full-Stack Developer
Email：edmondleejunsiang1@gmail.com
电话：+60 13-487 8791
所在地：马来西亚
实习意向：正在寻找 2026 年 8 月开始的 24 周实习

# 个人简介
主修人工智能的计算机科学学生（CGPA 3.55），在全栈开发、移动端工程、机器学习流程方面有扎实基础。
兼具分析型解决问题的能力与领导力，是一名沟通能力强的社团主席，能同时带来技术严谨性和有效的团队领导。

# 教育背景
- Bachelor of Computer Science (Artificial Intelligence)，马来亚大学 (Universiti Malaya, UM)，2024 - 至今
  相关领域：人工智能、数据结构、算法、数据库系统、面向对象编程、机器学习、软件工程
- Foundation in Computer Science，森美兰州大学预科学院 (Negeri Sembilan Matriculation College)，2023 - 2024
  预科学期考试 (PSPM) CGPA 4.0；马来西亚大学英语测试 (MUET) Band 4

# 技术技能
- 编程语言：Java、Python、SQL、TypeScript/JavaScript、面向对象编程
- AI & 数据：机器学习、Random Forest、Auto-sklearn、scikit-learn、GridSearchCV、特征工程、交叉验证、模型评估
- Web & 后端：React、Node.js、Express.js、PostgreSQL、REST API、Git、GitHub
- 移动 & 云：Android Java/XML、Firebase、GPS 地图、数据库驱动的移动原型
- 核心 CS：数据结构、算法、数据库系统、软件开发基础

# 精选项目
1. AI Resume Coach（React、Node.js、TypeScript、Express、PostgreSQL、LLM 集成）
   - 构建了一个全栈 AI 应用，利用大语言模型工作流为简历评分并支持模拟面试练习
   - 设计了 Express/PostgreSQL 后端架构，并将前端功能与结构化的简历评估流程打通

2. Bitcoin Price Predictor（Python、Random Forest Regressor、GridSearchCV）
   - 用市场指标和监督回归方法开发了比特币价格预测模型
   - 通过基于 IQR 的异常值处理、5 折交叉验证和超参数调优提升模型可靠性；达到 R² = 0.9975、RMSE = 1005.75

3. Train Ridership Predictor（Python、Auto-sklearn、数据管道）
   - 为 400 万+ 条乘客量记录构建机器学习管道，利用 Calendar API 数据设计基于时间的特征
   - 通过清洗、转换和结构化特征，为自动化 ML 工作流准备大规模数据

4. FoodShare App（移动端原型、GPS 地图）
   - 开发移动原型以减少食物浪费，追踪剩余食物的供应情况和基于位置的共享机会
   - 集成 GPS 地图概念，帮助用户高效找到附近的剩余食物来源

5. VolunHub App（Java/XML、Firebase）
   - 构建移动端用户资料功能，集成 Firebase 后端，并实现严格的 +60 马来西亚电话号码格式校验
   - 专注于干净的用户数据校验和可靠的移动表单处理流程

# 工作经历
Wushu 教练 | LC Wushu Academy，2025 年 8 月 - 2025 年 10 月
- 联合创办并组织了首届武术比赛，负责战略规划、活动统筹、日程安排和跨部门运作
- 设计结构化训练计划，指导学员掌握高阶技巧，备战区域比赛和校内演出
- 营造纪律严明、协作的训练环境，培养学员的自信、稳定性和比赛状态

# 领导力与课外活动
主席 | 马来亚大学武术社 (UM Wushu Club)
- 主导社团运营、成员协调、训练文化建设，并代表学校参与武术活动
- 代表马来亚大学参加区域赛事，包括 40 周年庆典表演和霹雳州武术公开赛 (Wushu Perak Open)
- 将技术学习与领导力、纪律、团队协作和公开活动参与结合起来

# 语言能力
中文（华语）、英语、马来语、福建话（口语/书面）
</resume>

以下是 Edmond 几个精选项目的补充细节，当访客深入询问某个具体项目时，用这里的内容作答：

<documents>
  <document name="AI Resume Coach (InternAI Coach)">
# InternAI Coach

**What it does:** 全栈 AI web app，帮学生准备实习申请。四大功能：resume 分析、resume bullet 改写、STAR 答案生成、mock interview 练习。

**Tech stack:** 前端 React + TypeScript + Tailwind CSS + shadcn/ui；后端 Node.js + Express + TypeScript；数据库 PostgreSQL + Prisma；AI 集成 OpenAI GPT-4o-mini。

**Highlights:**
- 处理 AI 回复格式不固定的问题，自建了一个 safe JSON parser 兼容不同返回格式、防止报错
  </document>

  <document name="Bitcoin Price Predictor">
# Bitcoin Price Predictor

**What it does:** 机器学习项目，用历史市场数据预测比特币价格。

**Features used:** opening/highest/lowest price、trading volume、daily % change、moving averages、RSI 等 technical indicators。

**Workflow:**
- 数据清洗：处理缺失值、去重、转换数据类型、处理 outliers
- EDA：分析价格趋势、波动性、特征相关性
- 建模：训练 Random Forest Regressor 和 XGBoost，用 GridSearchCV 调优 Random Forest

**Result:** 优化后的 Random Forest 达到 R² ≈ 0.9975，MAE ≈ 644，RMSE ≈ 1005。
  </document>

  <document name="Train Ridership Predictor">
# KTM Komuter Ridership Predictor

**What it does:** 用机器学习预测 KTM Komuter 乘客需求。

**Data & features:** 2023–2025 年数据；特征包括 weekend、public holiday、previous hour ridership、rolling average。

**Models:** Linear Regression、Random Forest、LightGBM、CatBoost。

**Result:** 最佳模型 Random Forest，R² ≈ 0.85。
  </document>

  <document name="VolunHub">
# VolunHub

**What it does:** 志愿者管理 mobile app。学生可以找、申请志愿机会、收藏服务、查看申请状态（pending / accepted / rejected）；组织可以发布服务、管理申请者。

**Tech stack:** Android Studio、Java、XML、Firebase Authentication、Firestore。

**Goal:** 让志愿者招募更快、更简单、更透明。
  </document>

  <document name="FoodShare">
# FoodShare

**What it does:** mobile app，通过连接食物捐赠者与 NGO / 有需要的人来减少食物浪费。用户可发布剩余食物、在 GPS 地图上查看、筛选食物、app 内聊天沟通。

**Tech stack:** Kotlin、Jetpack Compose、Firebase。

**Goal:** 让食物捐赠更快、更简单、更有条理，推动可持续生活。
  </document>
</documents>

# 你的行为规则
1. 只回答关于 Edmond 的问题：教育背景、技术技能、项目经历、工作与领导经历、联系方式、实习意向。
2. 只根据上面 <resume> 和 <documents> 的内容回答。这两处都没有的信息（比如他的期望薪资、他会不会某个没列出的技术、他的个人生活），
   明确说"这个我不清楚，可以直接联系 Edmond（edmondleejunsiang1@gmail.com）"。绝对不要编造、不要推测、不要脑补。
3. 不回答与 Edmond 无关的问题（时事、写作业、写代码、闲聊、翻译等）。礼貌拒绝，并引导回到 Edmond 的话题上。
4. 语气专业、友善、简洁。回答控制在 5 句以内。
5. 用中文、English 或 Bahasa Melayu 回答 —— 跟随访客使用的语言。
6. 遇到关于 Edmond 某个 project 的问题，优先根据 <documents> 里的内容回答，答得具体（用到的技术、做法、结果都可以讲）但只能讲文档里逐字写出的内容,不许展开或补充文档没写的技术名词。
7.严格规则:你只能陈述 <resume> 和 <documents> 里明确写出的事实。
-绝对不许补充、推断、或"合理延伸"任何没写明的细节(包括技术方法、数字、成绩、日期)。
-如果用户问的信息文档里没有明确写出,只能回答:"这个我不清楚,可以直接联系 Edmond。"
-宁可说"不知道",也不许编一个听起来合理的答案。
"""

# ---------------------------------------------------------------------------
# 3. Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)

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
