from dataclasses import dataclass


Coord = tuple[int, int]


@dataclass(frozen=True, slots=True)
class Move:
    start: Coord
    end: Coord
    is_capture: bool = False

    def uci(self) -> str:
        return f"{self.start[0]},{self.start[1]}-{self.end[0]},{self.end[1]}"
