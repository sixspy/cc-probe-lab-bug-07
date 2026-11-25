import os
import sqlite3
from pathlib import Path

数据目录 = Path(os.environ.get("数据目录", Path(__file__).resolve().parent.parent / "data"))
夹具目录 = Path(os.environ.get("夹具目录", Path(__file__).resolve().parent.parent.parent / "fixtures"))
库路径 = 数据目录 / "探栏.db"

# 测试故障注入钩子：签名 (sql) -> None，抛异常即模拟断连/边表失败
故障钩子 = None


class _探栏连接(sqlite3.Connection):
    def execute(self, sql, params=()):
        钩 = 故障钩子
        if 钩 is not None:
            钩(sql)
        return super().execute(sql, params)


def 连接() -> sqlite3.Connection:
    数据目录.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(库路径, timeout=15, factory=_探栏连接)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA busy_timeout = 15000")
    return c
