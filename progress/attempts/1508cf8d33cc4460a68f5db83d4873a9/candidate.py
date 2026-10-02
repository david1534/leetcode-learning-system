def longest_consecutive_streak(nums: list[int]) -> int:
    nums = set(nums)
    largestStreak = 0
    for currNum in nums:
        prevNum = currNum - 1
        if prevNum not in nums:
            currStreak = 1
            nextNum = currNum + 1
            while nextNum in nums:
                nextNum = nextNum + 1
                currStreak = currStreak + 1
            if currStreak > largestStreak:
                largestStreak = currStreak
    return largestStreak
