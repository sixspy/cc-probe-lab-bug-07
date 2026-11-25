#!/usr/bin/env python3
"""探栏 · 主边同票争用脚本。

对运行中的探栏服务（默认 http://127.0.0.1:8100）做：
  1) 并发同报文装载（双线程同票对撞）——期望恰好主边各一行，败者幂等驳回；
  2) 断连重试串行装载（边表失败后重试）——期望失败不留半态，重试齐全；
  3) 同票状态/回刷审计——半态为零、读轨 cutover_book、拒半态回刷打开。

用法：
  python3 /workspace/scripts/并发争用.py [base_url]
仅用标准库；服务端需已启动（docker compose up -d --build 或 hypercorn）。
"""
from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8100"


def _req(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    url = BASE + urllib.parse.quote(path, safe="/?=&")
    data = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}


def _一体(编号: str) -> dict:
    return {
        "批次编号": "争用脚本",
        "报文": [{
            "报文编号": 编号,
            "站点键": "站-河东",
            "指标键": "PM25",
            "读数": 36.6,
            "观测时": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }],
    }


def 并发同报文() -> bool:
    编号 = f"RACE-{uuid.uuid4().hex[:8]}"
    屏障 = threading.Barrier(2)
    结果: list[dict] = []
    锁 = threading.Lock()

    def 装():
        屏障.wait()
        try:
            _, rep = _req("POST", "/api/观测报文/装载", _一体(编号))
        except Exception as e:  # 网络异常也不允许吞成假绿
            rep = {"异常": str(e)}
        with 锁:
            结果.append(rep)

    t1 = threading.Thread(target=装)
    t2 = threading.Thread(target=装)
    t1.start(); t2.start(); t1.join(); t2.join()

    入栏 = sum(r.get("入栏", 0) for r in 结果)
    驳回 = sum(r.get("驳回", 0) for r in 结果)
    同票 = {r.get("同票") for r in 结果}
    ok = (入栏, 驳回) == (1, 1) and 同票 == {"主边同票"}
    print(f"[并发同报文 {编号}] 入栏={入栏} 驳回={驳回} 同票={同票} -> {'PASS' if ok else 'FAIL'}")
    return ok


def 断连重试() -> bool:
    # 正常装载代表"重试"票（边表失败由 pytest 故障钩子覆盖；线上验证幂等不双态）
    编号 = f"RETRY-{uuid.uuid4().hex[:8]}"
    c1, r1 = _req("POST", "/api/观测报文/装载", _一体(编号))
    c2, r2 = _req("POST", "/api/观测报文/装载", _一体(编号))
    ok = (
        c1 == 200 and r1.get("入栏") == 1
        and c2 == 200 and r2.get("驳回") == 1 and r2.get("入栏") == 0
        and r1.get("同票") == "主边同票"
    )
    print(f"[断连重试 {编号}] 首装入栏={r1.get('入栏')} 重试驳回={r2.get('驳回')} -> {'PASS' if ok else 'FAIL'}")
    return ok


def 同票审计() -> bool:
    _, 态 = _req("GET", "/api/同票/状态")
    _, 刷 = _req("POST", "/api/同票/回刷", {})
    ok = (
        态.get("可亮绿") is True
        and 态.get("半态笔数") == 0
        and 态.get("读轨") == "cutover_book"
        and 态.get("拒半态回刷") is True
        and 刷.get("拒绝") is False
    )
    print(f"[同票审计] 芯片={态.get('芯片')} 读轨={态.get('读轨')} "
          f"半态={态.get('半态笔数')} 拒刷={态.get('拒半态回刷')} 回刷={刷} -> {'PASS' if ok else 'FAIL'}")
    return ok


if __name__ == "__main__":
    print(f"目标服务: {BASE}")
    结果 = [并发同报文(), 断连重试(), 同票审计()]
    print("汇总:", "全部 PASS" if all(结果) else f"存在 FAIL: {结果}")
    sys.exit(0 if all(结果) else 1)
