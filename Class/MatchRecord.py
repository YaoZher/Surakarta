"""Durable local game records; never send files or certify a referee result."""
from datetime import datetime
import json
import os
from pathlib import Path
import re
import uuid


def load_match_info(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        raise ValueError("比赛信息必须是JSON对象")
    keys = ("event", "group", "round", "game_number", "black_team", "red_team")
    return {key: str(data.get(key, "")).replace("\n", " ").replace("\r", " ")[:120] for key in keys}


def _atomic_write(path, content):
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".pending")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class GameRecorder:
    def __init__(self, root, *, settings, metadata, initial_rows):
        now = datetime.now().astimezone()
        self.game_id = now.strftime("%Y%m%d_%H%M%S_%f") + "_" + uuid.uuid4().hex[:8]
        self.folder = Path(root) / self.game_id
        self.folder.mkdir(parents=True, exist_ok=False)
        self.started_at = now.isoformat()
        self.settings = dict(settings)
        self.metadata = dict(metadata)
        self.initial_rows = list(initial_rows)
        self.revision = 0

    def save(self, *, records, board_rows, status, operation, elapsed_ms, settings):
        self.revision += 1
        result = next((line for line in reversed(records) if line.startswith("#")), None)
        moves = []
        for line in records:
            match = re.fullmatch(r"([BR])([1-6])([A-F])-([1-6])([A-F])", line)
            if match:
                side, row1, col1, row2, col2 = match.groups()
                moves.append({"side": "black" if side == "B" else "red", "text": line,
                              "uci": f"{int(row1)-1},{ord(col1)-65}-{int(row2)-1},{ord(col2)-65}"})
        payload = {"schema": "surakarta-local-record-v1", "game_id": self.game_id,
                   "started_at": self.started_at, "saved_at": datetime.now().astimezone().isoformat(),
                   "revision": self.revision, "operation": operation, "metadata": self.metadata,
                   "initial_settings": self.settings, "current_settings": dict(settings),
                   "initial_rows": self.initial_rows, "final_rows": list(board_rows),
                   "records": list(records), "moves": moves, "status": status, "program_result": result,
                   "visible_elapsed_ms": dict(elapsed_ms),
                   "result_authority": "Program result or unadjudicated state only; players and referee confirm the competition result.",
                   "clock_scope": "Visible turn timers; AI internal balance separately charges search time. Neither establishes the referee's unconfirmed timing rule."}
        content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        # Append a durable full snapshot first, so a later snapshot-write failure
        # still leaves the move history in the journal.
        with (self.folder / "逐步备份.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        _atomic_write(self.folder / (self.game_id + ".json"), content)
        _atomic_write(self.folder / (self.game_id + ".txt"), self.text(payload))
        return self.folder / (self.game_id + ".txt")

    @staticmethod
    def text(payload):
        meta = payload["metadata"]
        value = lambda key: meta.get(key) or "未填写"
        result = payload["program_result"] or "未在程序内判定，请按双方/裁判确认结果报分"
        header = [f"{payload['started_at']}|{meta.get('event') or '苏拉卡尔塔对局'}",
                  f"组别：{value('group')}|轮次：{value('round')}|第几局：{value('game_number')}",
                  f"先手（黑方）：{value('black_team')}|后手（红方）：{value('red_team')}",
                  f"状态：{payload['status']}|结果：{result}",
                  f"对局ID：{payload['game_id']}|已记录走法：{len(payload['moves'])}", ""]
        return "\n".join([*header, *payload["records"], ""])

    def export(self):
        source = self.folder / (self.game_id + ".json")
        payload = json.loads(source.read_text(encoding="utf-8"))
        suffix = datetime.now().strftime("%H%M%S_%f") + "_" + uuid.uuid4().hex[:6]
        prefix = self.folder / (self.game_id + "_导出_" + suffix)
        content = self.text(payload)
        with prefix.with_suffix(".txt").open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        with prefix.with_suffix(".json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        return prefix.with_suffix(".txt")
