# Edge Cases Test File

Testing various edge cases for the Markdown scanner.

## Empty Sections

### Empty Heading Content

Some headings might be empty or contain only whitespace.

###

This heading above has no text.

## Code Blocks

### Multiple Languages

```javascript
const greeting = "Hello, World!";
console.log(greeting);
```

```rust
fn main() {
    println!("Hello, Rust!");
}
```

```go
package main

import "fmt"

func main() {
    fmt.Println("Hello, Go!")
}
```

### Code Without Language

```
This code block has no language specified.
It should still be detected.
```

### Indented Code Blocks

Regular paragraph text here.

    This is an indented code block.
    It uses 4 spaces for indentation.
    No language tag is possible.

Back to normal text.

## Nested Headings

### Level 3
#### Level 4
##### Level 5
###### Level 6

Deep nesting of headings.

## Special Characters

### Heading with `inline code`

### Heading with **bold** and *italic*

### Heading with [links](https://example.com)

## Mixed Setext and ATX

Setext Level 1
==============

Content under setext heading.

### ATX Level 3

More content.

Setext Level 2
--------------

### Another ATX Level 3

## Lists and Code

Ordered list:

1. First item
2. Second item
3. Third item with code:

```python
def example():
    pass
```

Unordered list:

- Item one
- Item two
- Item three

## Consecutive Code Blocks

```python
first = "block"
```

```python
second = "block"
```

```javascript
const third = "block";
```

## Headings After Code

```bash
echo "Code first"
```

### Then a heading

## Empty Code Blocks

```python
```

```
```

## Long Code Block

```python
class ComplexClass:
    def __init__(self):
        self.value = 0

    def method_one(self):
        return self.value

    def method_two(self, x):
        self.value = x

    def method_three(self):
        for i in range(10):
            self.value += i
        return self.value
```

## Unicode and Special Characters

### Heading with émojis and ñ characters

```python
# Python with unicode
name = "Björk"
greeting = "Привет"
```

## Blank Lines

### Section with Many Blanks


Content after blank lines.


## Final Section

===

This equals sign is not a valid setext underline (too short).

### Last Heading

End of file.
