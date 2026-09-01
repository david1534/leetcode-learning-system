"""
Pair Sum Indices
================
Difficulty: Easy | Suggested time: 20 minutes

Problem
-------
Return the two indices of distinct values that add to target. Exactly one solution
exists; return indices in increasing order.

Function signature
------------------
pair_sum_indices(nums: list[int], target: int) -> list[int]

Parameters
----------
nums (list[int]): The integers whose positions may form the required pair.
target (int): The sum the two selected values must equal.

Returns
-------
list[int]: The two distinct indices in increasing order.

Constraints
-----------
- 2 <= len(nums) <= 100000
- Exactly one valid pair exists

Example 1
---------
nums = [7, 2, 11, 5]
target = 7
Output: [1, 3]
Explanation: nums[1] + nums[3] equals 2 + 5 = 7, so return [1, 3].

Related practice
----------------
https://leetcode.com/problems/two-sum/
"""


def pair_sum_indices(nums: list[int], target: int) -> list[int]:
    hashMap = {}
    for numInd, numVal in enumerate(nums):
        numComp = target - numVal
        if numComp not in hashMap:
            hashMap[numVal] = numInd
        elif numComp in hashMap:
            ind1 = hashMap[numComp]
            ind2 = numInd
    output = [ind1, ind2]
    return output
