def valid_partial_grid(board: list[str]) -> bool:
    rows = [set() for _ in range (9)]
    columns = [set() for _ in range (9)]
    boxes = [set() for _ in range (9)]

    for currRow, string in enumerate(board):
        for currColumn, currCell in enumerate(string):
            currBox = 3 * (currRow // 3) + (currColumn // 3)
            if currCell == ".":
                continue
            elif currCell in (rows[currRow] or columns[currColumn] or boxes[currBox]):
                return False
            else:
                rows[currRow].add(currCell)
                columns[currColumn].add(currCell)
                boxes[currBox].add(currCell)
    return True
