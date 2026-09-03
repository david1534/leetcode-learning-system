"""
Product of the Other Positions
==============================
Difficulty: Medium | Suggested time: 25 minutes

Problem
-------
Return an array where result[i] is the product of all nums values except nums[i]. Do not
use division.

Function signature
------------------
product_of_others(nums: list[int]) -> list[int]

Parameters
----------
nums (list[int]): Values used to form each position's product.

Returns
-------
list[int]: Products of every value except the one at the corresponding index.

Constraints
-----------
- 2 <= len(nums) <= 100000
- Products fit in Python integers

Example 1
---------
nums = [1, 2, 3, 4]
Output: [24, 12, 8, 6]
Explanation: For index 0, multiply 2 * 3 * 4 = 24; apply the same rule at every index.

Related practice
----------------
https://leetcode.com/problems/product-of-array-except-self/
"""


def product_of_others(nums: list[int]) -> list[int]:
    raise NotImplementedError
