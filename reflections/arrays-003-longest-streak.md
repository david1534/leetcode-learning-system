# Longest Consecutive Streak

## Approach

### Initial reasoning

- Approach: Create a set to deduplicate the list. Iterate through the set; use n - 1 to identify the start of a streak, then use n + 1 repeatedly to continue and count that streak. Track the maximum streak length.
- Why it fit: Set membership is average O(1), and starting only where the predecessor is absent avoids recounting a streak from every value.
- Invariant or key belief: A streak is counted only from a value n for which n - 1 is absent; while extending it, each successive integer is present in the set and the counter equals the streak length seen so far.
- Expected complexity: O(n) average time and O(n) space for the set.
- Edge case: If every list element has the same value, deduplication leaves one value and the longest streak is 1; an empty list should produce 0.
- Recall quality: complete

### Final approach

Convert the input to a set, identify each streak start by checking that n - 1 is absent, then count forward through n + 1 values while tracking the maximum length.

## Key invariant or insight

A consecutive streak should be counted only from its smallest value, so each distinct value participates in at most one forward scan.

## Complexity

- Time: `O(n) average time`
- Space: `O(n)`

## Mistakes and lessons

The initial algorithm and invariant were correct. During implementation, I reversed the predecessor condition and initialized the maximum to 1 even though empty input is allowed. Trace the streak-start condition and choose accumulator defaults that represent an empty result.

## Assistance received

- Formal hints invoked: 0
- Highest assistance level: minor
- Minor (conversation): Identified an isolated reversed predecessor condition after the recorded approach and invariant had already stated the correct streak-start rule.
- Minor (conversation): Identified the empty-input initialization edge case: the loop does not run, so initializing the maximum streak to 1 returns a nonzero streak for an empty list.

Minor implementation help identified the reversed predecessor condition and the empty-input initialization issue. No hint, replacement algorithm, invariant, representation, or pseudocode was supplied.

## Rating rationale

- Enforced maximum rating: Good
- Evidence: It passed with only minor implementation help; multiple checkpoints or extra time were used.

Good is appropriate because I independently reconstructed the correct core algorithm and invariant, then passed all cases after three checkpoints and two localized implementation corrections.
