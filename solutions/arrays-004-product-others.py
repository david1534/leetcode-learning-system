def product_of_others(nums: list[int]) -> list[int]:
    # nums:     [1,2,3,4]
    # left:     [1,1,2,6]
    # right:    [1,4,12,24]
    # rightRev: [24,12,4,1]
    # ----
    # Output:   [24,12,8,6]

    leftProd = []
    rightProd = []
    Output = []
    numLength = len(nums)               # numLength = 4

    for currInd in range(numLength):    # range = 0,1,2,3
        if currInd == 0:
            prevNum = 1
            runningProd = 1
        else:
            prevNum = nums[currInd-1]
            runningProd = leftProd[-1]
        nextNum = runningProd * prevNum
        leftProd.append(nextNum)    # [1,1,2,6]

    for currInd in range((numLength-1),-1,-1):   # range = 3,2,1,0
        if currInd == (numLength-1):
            prevNum = 1
            runningProd = 1
        else:
            prevNum = nums[currInd+1]
            runningProd = rightProd[-1]
        nextNum = runningProd * prevNum
        rightProd.append(nextNum)   # [1,4,12,24]
    rightProd.reverse()

    for currInd in range(numLength):
        nextNum = leftProd[currInd] * rightProd[currInd]
        Output.append(nextNum)
    return Output