# Learning reflection

at the current index, we cannot simply multiply the product of everything to the left with the product with everything to the right even though mathematically we will arrive at the correct output. This method is inefficient with an O(n^2) time complexity. We take a running forward pass (left) and a running backward pass (right) to gather the left and right products in one pass. We can then multiply these running passes together to arrive at the same output but more efficiently

Activity: implement. Recall: again. Assistance: substantial.
Explanation recorded: True. Constraints checked: True.
