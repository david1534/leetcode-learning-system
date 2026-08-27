# Pair Sum Indices

## Approach

Traverse the array once while storing previously seen values and their indices in a hashmap. For each value, calculate target minus the value and return the earlier index when that complement is already in the hashmap.

## Key invariant or insight

Before each iteration, the hashmap contains previously seen values and their indices. Checking for the complement before storing the current value guarantees two distinct indices.

## Complexity

- Time: `O(n) average time`
- Space: `O(n)`

## Mistakes and lessons

I initially stored complements as keys, overwrote an earlier duplicate index, and used absolute value, which loses the sign needed for negative complements. I learned to keep the hashmap meaning consistent and use target - value. I had seen this problem before, perhaps a couple of months ago.

## Assistance received

The hints helped me switch to a simpler previously-seen value-to-index hashmap and recognize that the complement must preserve its sign. I still needed several debugging iterations to apply those ideas correctly.

## Rating rationale

The original review recorded Hard, but the evidence shows I did not independently reconstruct a working approach. Two formal hints redirected the representation and clarified the complement calculation, followed by several debugging iterations. Passing the tests demonstrated eventual correctness, not independent recall. The effective rating is therefore corrected to Again.
