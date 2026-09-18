workflowx/
├── .env                # 本地开发环境变量(不要提交git)
├── .env.example        # 示例环境变量，提交git，给别人参考
├── .gitignore
├── pyproject.toml      # uv/poetry依赖管理，替代requirements.txt
├── README.md           # 项目介绍、启动步骤、接口文档地址
├── Dockerfile
├── docker-compose.yml
├── app/
│   ├── __init__.py
│   ├── main.py                 # 程序入口，创建fastapi实例，注册路由、中间件、异常处理器
│   ├── core/                   # 【核心公共层】与业务无关，整个项目基础组件
│   │   ├── __init__.py
│   │   ├── config.py           # 读取.env，全局配置类(JWT密钥、数据库url、环境模式)
│   │   ├── security.py        # JWT签发、解析、密码hash、verify密码
│   │   ├── exceptions.py       # 自定义业务异常类，如UserExistError、PermissionDeniedError
│   │   ├── dependencies.py     # FastAPI依赖注入：get_current_user、require_permission
│   │   └── middlewares.py      # 中间件：请求日志、CORS
│   ├── common/                 # 【通用组件】少量通用模型、工具函数
│   │   ├── __init__.py
│   │   ├── schemas.py          # 基础Pydantic模型：分页基类、基础返回模型
│   │   └── utils.py            # 工具函数：时间处理、uuid生成
│   ├── db/                     # 数据库层
│   │   ├── __init__.py
│   │   ├── base.py             # SQLAlchemy Base模型基类
│   │   ├── session.py          # 数据库session会话，get_db依赖
│   │   └── migrations/         # alembic数据库迁移文件夹(版本迁移脚本)
│   ├── models/                 # ORM数据库模型，表映射，**按业务模块拆分**
│   │   ├── __init__.py
│   │   ├── user.py             # 用户表、角色表、RBAC角色权限关联表
│   │   ├── team.py             # 团队表、团队成员关联表
│   │   ├── project.py         # 项目表、项目成员关联表
│   │   ├── task.py             # workflow表、任务表
│   │   └── system.py          # 通知表、操作日志表
│   ├── api/                    # 路由层，只做参数接收、调用service，不写业务逻辑
│   │   ├── __init__.py
│   │   ├── deps.py             # api层局部依赖
│   │   ├── v1/                 # /api/v1 版本控制，方便后续v2迭代
│   │   │   ├── __init__.py
│   │   │   ├── auth.py         # 登录、注册、刷新token
│   │   │   ├── users.py        # 用户管理
│   │   │   ├── teams.py        # 团队管理
│   │   │   ├── projects.py     # 项目管理
│   │   │   ├── tasks.py        # 工作流、任务分配、任务完成
│   │   │   └── system.py      # 通知、操作日志
│   └── services/               # ✨【业务逻辑层】所有核心业务写在这里！！重点！
│       ├── __init__.py
│       ├── auth_service.py     # 注册逻辑、登录校验、生成token
│       ├── user_service.py     # 用户增改查、角色分配
│       ├── team_service.py     # 创建团队、添加团队成员、修改团队权限
│       ├── project_service.py  # 创建项目、添加项目成员、修改项目权限
│       ├── task_service.py     # 创建任务、分配任务、完成任务、权限校验
│       └── system_service.py  # 发送站内通知、记录操作日志
└── tests/                      # 简单单元测试，简历加分，不用写很全
    ├── __init__.py
    ├── test_auth.py
    └── test_ticket.py


## 性能基线（本地环境，2026-09）

**测试环境**：
- 硬件：本机（4 核）
- uvicorn: 4 workers
- 连接池: pool_size=5, max_overflow=5
- Postgres: max_connections=100

**接口**: GET /api/v1/auth/me

| VU | med | p95 | 吞吐 | 状态 |
|----|-----|-----|------|------|
| 50 | 7.19ms | 11.97ms | 44/s | 轻松 |
| 100 | 5.88ms | 10.49ms | 82/s | 轻松 |
| 150 | 5.95ms | 54.78ms | 137/s | 有压力 |
| 200 | 5.7ms | 51.26ms | 172/s | 有压力 |
| 250 | 6.14ms | 164.44ms | 214/s | 超阈值 |

**结论**：
- 稳定并发上限：约 200 VU
- 稳定吞吐：约 170 req/s
- 优化历程：连接池 20+30 → 5+5，workers 1 → 4


