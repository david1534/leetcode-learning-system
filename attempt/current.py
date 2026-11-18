def most_frequent_values(nums: list[int], k: int) -> list[int]:
    freqMap = {}
    for currNum in nums:
        if currNum not in freqMap:
            freqMap[currNum] = 1
        else:
            freqMap[currNum] += 1
    sortedKeys = sorted(freqMap.values())
            
