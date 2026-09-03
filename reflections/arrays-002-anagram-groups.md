# Group Rearranged Words

## Approach

### Initial reasoning

- Approach: For each word, use ord() to map characters into a 26-entry frequency array, convert that array to a hashable tuple, and use the tuple as a hashmap key whose value is an appended list of matching words so insertion order is preserved.
- Why it fit: Words with the same character frequencies produce the same tuple key, so they are accumulated in the same hashmap bucket.
- Invariant or key belief: Not yet explicitly stated by the learner.
- Expected complexity: Learner stated O(n), describing processing all characters in the input; the variables and space bound still need clarification.
- Edge case: All words are duplicates and therefore belong to the same group.
- Recall quality: partial

### Final approach

For each word, create a fresh 26-entry character-frequency array using ord(char) - ord("a"). Convert that array to a tuple and use it as a hashmap key. Initialize a list for a signature the first time it appears, append each word to its signature's bucket, and return the buckets in insertion order.

## Key invariant or insight

After processing the first k words, each frequency-signature key maps to exactly the processed word occurrences with that signature, including duplicates, in their original input order.

## Complexity

- Time: `O(N + C), where N is the number of words and C is the total number of characters`
- Space: `O(N) auxiliary grouping space, or O(N + C) when stored word data and output are included`

## Mistakes and lessons

The core frequency-tuple grouping approach was recalled independently. The invariant and complexity notation needed refinement. The first checkpoint exposed an implementation slip: dictionary assignment creates a missing key-value entry, while lookup requires the key to exist before append can mutate the retrieved list.

## Assistance received

- Formal hints invoked: 0
- Highest assistance level: guided
- Minor (conversation): Clarified that fixed 26-entry signature work per word makes time O(N + C), and auxiliary grouping space is O(N + G), typically O(N), rather than stating only O(C).
- Guided (conversation): Used targeted questions to refine the invariant: after k words, each frequency-signature bucket contains exactly those processed word occurrences sharing that signature, in original order.
- Minor (conversation): Pointed the learner to the first append for a previously unseen frequency-tuple key and asked them to reason about bucket initialization.
- Minor (conversation): Explained the isolated Python hashmap initialization step: if a frequency key is absent, assign it an empty list before appending the word.
- Minor (conversation): Explained the distinction between dictionary lookup and assignment: assigning an empty list creates a missing key-value entry, after which lookup returns a list that append can mutate.

Guided questions refined the invariant. Minor coaching clarified the complexity variables and explained how to initialize a new hashmap bucket before appending. No formal hints or replacement solution were used.

## Rating rationale

- Enforced maximum rating: Hard
- Evidence: It passed with guided algorithmic help or targeted debugging.

Hard is appropriate because the frequency-signature algorithm and implementation were independently reconstructed, but guided help was needed to complete the invariant. The first checkpoint passed 1 of 4 cases, and the corrected solution passed 4 of 4 cases on the second checkpoint.
