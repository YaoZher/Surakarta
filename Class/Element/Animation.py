import math


def interpolate_line(start: tuple[int, int], end: tuple[int, int], frames: int) -> list[tuple[int, int]]:
    if frames <= 1:
        return [end]

    start_x, start_y = start
    end_x, end_y = end
    points: list[tuple[int, int]] = []
    for frame in range(frames):
        ratio = frame / (frames - 1)
        x = round(start_x + (end_x - start_x) * ratio)
        y = round(start_y + (end_y - start_y) * ratio)
        points.append((x, y))
    return points


def interpolate_capture_route(
    route: tuple[tuple[int, int], ...],
    *,
    board_origin: tuple[int, int],
    spacing: int,
    frames: int,
) -> list[tuple[int, int]]:
    if not route:
        return []
    if frames <= 1:
        return [_coord_to_pixel(route[-1], board_origin, spacing)]

    dense: list[tuple[int, int]] = [_coord_to_pixel(route[0], board_origin, spacing)]
    index = 0
    while index < len(route) - 1:
        next_coord = route[index + 1]
        if _in_bounds(next_coord):
            dense.append(_coord_to_pixel(next_coord, board_origin, spacing))
            index += 1
            continue

        arc_end = index + 1
        while arc_end < len(route) and not _in_bounds(route[arc_end]):
            arc_end += 1
        if arc_end >= len(route) or arc_end - index != 3:
            dense.append(_coord_to_pixel(next_coord, board_origin, spacing))
            index += 1
            continue

        arc_points = _sample_three_quarter_arc(
            route[index],
            route[index + 1],
            route[index + 2],
            route[arc_end],
            board_origin,
            spacing,
        )
        dense.extend(arc_points[1:])
        index = arc_end

    return _resample_polyline(dense, frames)


def _sample_three_quarter_arc(
    start: tuple[int, int],
    first_quarter: tuple[int, int],
    opposite: tuple[int, int],
    end: tuple[int, int],
    board_origin: tuple[int, int],
    spacing: int,
) -> list[tuple[int, int]]:
    center_row = (start[0] + opposite[0]) / 2.0
    center_col = (start[1] + opposite[1]) / 2.0
    radius = math.hypot(start[0] - center_row, start[1] - center_col)
    start_angle = math.atan2(start[0] - center_row, start[1] - center_col)
    quarter_angle = math.atan2(
        first_quarter[0] - center_row,
        first_quarter[1] - center_col,
    )
    delta = _normalize_angle(quarter_angle - start_angle)
    direction = 1.0 if delta > 0 else -1.0

    samples = 37
    points: list[tuple[int, int]] = []
    for sample in range(samples):
        ratio = sample / (samples - 1)
        angle = start_angle + direction * 1.5 * math.pi * ratio
        row = center_row + radius * math.sin(angle)
        col = center_col + radius * math.cos(angle)
        points.append(
            (
                round(board_origin[0] + col * spacing),
                round(board_origin[1] + row * spacing),
            )
        )
    points[0] = _coord_to_pixel(start, board_origin, spacing)
    points[-1] = _coord_to_pixel(end, board_origin, spacing)
    return points


def _resample_polyline(points: list[tuple[int, int]], frames: int) -> list[tuple[int, int]]:
    if not points:
        return []
    if frames <= 1:
        return [points[-1]]

    cumulative = [0.0]
    for first, second in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + math.dist(first, second))
    total = cumulative[-1]
    if total == 0:
        return [points[-1]] * frames

    result: list[tuple[int, int]] = []
    segment = 0
    for frame in range(frames):
        target = total * frame / (frames - 1)
        while segment < len(cumulative) - 2 and cumulative[segment + 1] < target:
            segment += 1
        start_distance = cumulative[segment]
        end_distance = cumulative[segment + 1]
        ratio = 0.0 if end_distance == start_distance else (
            (target - start_distance) / (end_distance - start_distance)
        )
        x = round(points[segment][0] + (points[segment + 1][0] - points[segment][0]) * ratio)
        y = round(points[segment][1] + (points[segment + 1][1] - points[segment][1]) * ratio)
        result.append((x, y))
    return result


def _coord_to_pixel(
    coord: tuple[int, int],
    board_origin: tuple[int, int],
    spacing: int,
) -> tuple[int, int]:
    row, col = coord
    return board_origin[0] + col * spacing, board_origin[1] + row * spacing


def _in_bounds(coord: tuple[int, int]) -> bool:
    return 0 <= coord[0] < 6 and 0 <= coord[1] < 6


def _normalize_angle(value: float) -> float:
    while value <= -math.pi:
        value += 2 * math.pi
    while value > math.pi:
        value -= 2 * math.pi
    return value
