def most_frequent_values(nums: list[int], k: int) -> list[int]:
    freqMap = dict()
    outputMap = dict()
    outputList = list()
    for currNum in nums:
        if currNum not in freqMap:
            freqMap[currNum] = 1
        else:
            freqMap[currNum] += 1
    for num, freq in freqMap.items():
        if freq not in outputMap:
            outputMap[freq] = list()
        outputMap[freq].append(num)
    for currFreq in range(len(nums),0,-1):
        if currFreq in outputMap:
            if k == 0:
                return outputList
            else:
                for currVal in outputMap[currFreq]:
                    outputList.append(currVal)
                    k -= 1