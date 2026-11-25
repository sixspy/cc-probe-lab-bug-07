"""栏贯验：已汇总缓冲报文数 == 汇总账报文数之和；主边同票半态计入撕裂。"""
from __future__ import annotations
from app.db import 连接
from app.seed import 此刻
from app.services import 同票


def _取数(conn) -> dict:
    在栏 = conn.execute(
        "SELECT COUNT(*) AS c FROM 入栏缓冲 WHERE 命运='在栏'"
    ).fetchone()["c"]
    已汇总缓冲 = conn.execute(
        "SELECT COUNT(*) AS c FROM 入栏缓冲 WHERE 命运='已汇总'"
    ).fetchone()["c"]
    汇总报文 = conn.execute(
        "SELECT COALESCE(SUM(报文数),0) AS c FROM 站点汇总账"
    ).fetchone()["c"]
    坏点 = conn.execute("SELECT COUNT(*) AS c FROM 坏点匣").fetchone()["c"]
    半态 = len(同票._半态查询(conn))
    数对齐 = int(已汇总缓冲) == int(汇总报文)
    return {
        "在栏": 在栏,
        "已汇总缓冲": int(已汇总缓冲),
        "汇总报文": int(汇总报文),
        "坏点": 坏点,
        "半态笔数": 半态,
        "是否对齐": bool(数对齐 and 半态 == 0),
    }


def _说明(数: dict) -> str:
    if not 数["是否对齐"]:
        if 数["半态笔数"] > 0:
            return (
                f"撕裂：主边半态{数['半态笔数']}笔（主有边无/边有主无）；"
                f"已汇总缓冲={数['已汇总缓冲']} 汇总报文={数['汇总报文']}"
            )
        return f"撕裂：已汇总缓冲={数['已汇总缓冲']} 汇总报文={数['汇总报文']}"
    return "入栏已汇总与站点汇总报文数一致，主边同票无半态"


def 跑一次() -> dict:
    conn = 连接()
    try:
        数 = _取数(conn)
        说明 = _说明(数)
        时刻 = 此刻()
        conn.execute(
            """INSERT INTO 栏贯验(时刻,在栏笔数,汇总报文数,坏点笔数,是否对齐,说明)
               VALUES (?,?,?,?,?,?)""",
            (时刻, 数["在栏"], 数["汇总报文"], 数["坏点"], 1 if 数["是否对齐"] else 0, 说明),
        )
        conn.commit()
        return {"时刻": 时刻, **数, "说明": 说明}
    finally:
        conn.close()


def 只读快照() -> dict:
    """不落库的贯验快照，供页面预览。"""
    conn = 连接()
    try:
        return _取数(conn)
    finally:
        conn.close()
