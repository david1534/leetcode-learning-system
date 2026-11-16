def pair_sum_indices(nums: list[int], target: int) -> list[int]:
    compMap = {}
    numLength = len(nums)
    for currInd in range(numLength):
        currNum = nums[currInd]
        currComp = target - currNum
        if currNum not in compMap:
            compMap[currComp] = currInd     # [0:0,5:1,-3:2]
        else:
            ind1 = compMap[currNum]
            ind2 = currInd
            Output = [ind1,ind2]
            return Output


