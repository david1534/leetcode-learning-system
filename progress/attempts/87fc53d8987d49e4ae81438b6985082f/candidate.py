def product_of_others(nums: list[int]) -> list[int]:
    # nums =            [1   2   3  4 ]
    # runningList =     [1   1   2  6 ]
    # runningList2 =    [1   2   6  24]
    # output =          [24  12  8  6 ]
    runningProd = 1
    runningList = [1]
    for currIndex in range(len(nums) - 1):
        currNum = nums[currIndex]
        runningProd = currNum * runningProd
        runningList.append(runningProd)
        
