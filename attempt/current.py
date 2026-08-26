"""Pair Sum Indices

Return the two indices of distinct values that add to target. Exactly one solution exists; return indices in increasing order.

Examples:
[
  {
    "input": [
      [
        7,
        2,
        11,
        5
      ],
      7
    ],
    "output": [
      1,
      3
    ]
  }
]

Related practice: https://leetcode.com/problems/two-sum/
"""


def pair_sum_indices(inputArray, target):
    seen = {}
    for index, value in enumerate(inputArray):
        complement = abs(value - target)
        if value in seen: 
            compIndex = seen[value]
            return [compIndex, index]
        elif value not in seen:
            seen[complement] = index
    raise NotImplementedError

# input = [7,7,2,5]
# targ = 9
# seen = [2:0]
# index = 1
# value = 7
# complement = 2
