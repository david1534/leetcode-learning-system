def longest_consecutive_streak(nums: list[int]) -> int:
    listSet = set(nums)
    largestStreak = 0
    for num in listSet:
        prevNum = num - 1
        if prevNum not in listSet:
            currStreak = 1
            nextNum = num + 1
            while nextNum in listSet:
                currStreak += 1
                nextNum += 1
            if currStreak > largestStreak:
                largestStreak = currStreak
    return largestStreak
