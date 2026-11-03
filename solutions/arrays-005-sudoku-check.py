def valid_partial_grid(board: list[str]) -> bool:

    row_sets = [set() for _ in range(9)]
    col_sets = [set() for _ in range(9)]
    box_sets = [set() for _ in range(9)]

    for r, row in enumerate(board):
        for c, cell in enumerate(row):
            if cell == '.':
                continue
            box_id = (r // 3) * 3 + (c // 3)
            # Check row_sets[r], col_sets[c], and box_sets[box_id].
            # If none contains cell, add it to all three.
            if cell in (row_sets[r] or col_sets[c] or box_sets[box_id]):
                return False
            else:
                row_sets[r].add(cell)
                col_sets[c].add(cell)
                box_sets[box_id].add(cell)
    return True