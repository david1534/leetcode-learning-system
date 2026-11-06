def product_of_others(nums: list[int]) -> list[int]:
    forwardPass = [1]
    backwardPass = [1]
    output = []
    rightProduct = 1
    leftProduct = 1
    numLen = (len(nums)-1)                      # numLen = 3
    for f in range(numLen):                     # f = 0,1,2
        leftProduct = nums[f] * leftProduct     # leftProduct = 1,2,6
        forwardPass.append(leftProduct)         # forwardPass = [1,1,2,6]
        b = numLen - f                          # b = 3,2,1
        rightProduct = nums[b] * rightProduct   # rightProduct = 4,12,24
        backwardPass.append(rightProduct)       # backwardPass = [1,4,12,24]
    backwardPass.reverse()
    for i in range(len(nums)):
        product = forwardPass[i] * backwardPass[i]
        output.append(product)
    return output
