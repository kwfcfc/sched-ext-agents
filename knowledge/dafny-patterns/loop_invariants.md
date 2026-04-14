# Common Loop Invariant Patterns for Dafny

## Pattern 1: Linear scan over a sequence

```dafny
var i := 0;
var result := initial;
while i < |s|
  invariant 0 <= i <= |s|
  invariant result == f(s[..i])   // result is correct for prefix processed so far
  decreases |s| - i
{
  result := update(result, s[i]);
  i := i + 1;
}
// Post: result == f(s[..|s|]) == f(s)
```

## Pattern 2: Finding minimum in a sequence

```dafny
var min_idx := 0;
var i := 1;
while i < |s|
  invariant 1 <= i <= |s|
  invariant 0 <= min_idx < i
  invariant forall j :: 0 <= j < i ==> s[min_idx] <= s[j]
  decreases |s| - i
{
  if s[i] < s[min_idx] { min_idx := i; }
  i := i + 1;
}
```

## Pattern 3: Sorted insertion (critical for scheduler)

```dafny
method SortedInsert(sorted: seq<int>, val: int) returns (result: seq<int>)
  requires forall i, j :: 0 <= i < j < |sorted| ==> sorted[i] <= sorted[j]
  ensures forall i, j :: 0 <= i < j < |result| ==> result[i] <= result[j]
  ensures multiset(result) == multiset(sorted) + multiset{val}
{
  var idx := 0;
  while idx < |sorted| && sorted[idx] <= val
    invariant 0 <= idx <= |sorted|
    invariant forall i :: 0 <= i < idx ==> sorted[i] <= val
    decreases |sorted| - idx
  { idx := idx + 1; }
  result := sorted[..idx] + [val] + sorted[idx..];
}
```

## Pattern 4: Map iteration (BPF map scan)

Since Dafny maps don't have iteration order, convert to a sequence of keys first:

```dafny
var keys := SetToSeq(m.Keys);
var i := 0;
while i < |keys|
  invariant 0 <= i <= |keys|
  invariant forall j :: 0 <= j < i ==> P(keys[j], m[keys[j]])
  decreases |keys| - i
{
  var k := keys[i];
  assert k in m;
  // ... process m[k] ...
  i := i + 1;
}
```

## Pattern 5: Bounded countdown (starvation budget)

```dafny
ghost var budget := STARVATION_BOUND;
while condition
  invariant budget >= 0
  invariant budget == STARVATION_BOUND - elapsed
  decreases budget
{
  // Each iteration consumes some budget
  budget := budget - cost;
}
```

## Common Pitfalls

1. **Forgetting `decreases`**: Every while loop needs one. For nested loops, use a tuple: `decreases outer - i, inner - j`

2. **Invariant too weak**: If Dafny can't prove the postcondition, your invariant probably doesn't capture enough state. Add intermediate `assert` statements to find where the proof breaks.

3. **Invariant not preserved**: The invariant must hold after every iteration. A common mistake: updating `i` before updating `result`, making the invariant temporarily false.

4. **Trigger issues**: `forall` quantifiers need triggers. If verification times out, try adding manual triggers:
   ```dafny
   forall i {:trigger s[i]} :: 0 <= i < |s| ==> s[i] > 0
   ```
