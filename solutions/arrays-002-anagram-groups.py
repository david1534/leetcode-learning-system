"""
Group Rearranged Words
======================
Difficulty: Medium | Suggested time: 25 minutes

Problem
-------
Group lowercase words that are rearrangements of the same letters. Preserve the
first-seen group order and word order within each group.

Function signature
------------------
group_rearranged_words(words: list[str]) -> list[list[str]]

Parameters
----------
words (list[str]): Lowercase words to group by their letters.

Returns
-------
list[list[str]]: Anagram groups preserving first-seen group and word order.

Constraints
-----------
- 0 <= len(words) <= 10000
- Words contain lowercase English letters

Example 1
---------
words = ['eat', 'tea', 'tan', 'ate']
Output: [['eat', 'tea', 'ate'], ['tan']]
Explanation: eat, tea, and ate share the same letters; tan forms the next group.

Related practice
----------------
https://leetcode.com/problems/group-anagrams/
"""


def group_rearranged_words(words: list[str]) -> list[list[str]]:
    wordGroup = {}
    Output = []
    for word in words:
        charList = [0] * 26
        for char in word:
            num = ord(char) - ord("a")
            charList[num] += 1
        charTuple = tuple(charList)
        if charTuple not in wordGroup:
            wordGroup[charTuple] = []
        wordGroup[charTuple].append(word)
    for groupKey in wordGroup.keys():
        currGroup = list(wordGroup[groupKey])
        Output.append(currGroup)
    return Output
