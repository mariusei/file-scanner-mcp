// Package edgecases tests edge cases for Go scanner
package edgecases

import (
	"context"
	"sync"
)

// Generic type with type parameters (Go 1.18+)
type GenericContainer[T any] struct {
	items []T
	mu    sync.Mutex
}

// Add adds an item to the container
func (gc *GenericContainer[T]) Add(item T) {
	gc.mu.Lock()
	defer gc.mu.Unlock()
	gc.items = append(gc.items, item)
}

// Get retrieves an item by index
func (gc *GenericContainer[T]) Get(index int) (T, bool) {
	gc.mu.Lock()
	defer gc.mu.Unlock()
	if index >= 0 && index < len(gc.items) {
		return gc.items[index], true
	}
	var zero T
	return zero, false
}

// Multi-return function with named returns
func DivideWithRemainder(dividend, divisor int) (quotient int, remainder int, err error) {
	if divisor == 0 {
		return 0, 0, nil
	}
	quotient = dividend / divisor
	remainder = dividend % divisor
	return
}

// Variadic function
func Sum(numbers ...int) int {
	total := 0
	for _, n := range numbers {
		total += n
	}
	return total
}

// ChannelProcessor demonstrates channel and goroutine usage
type ChannelProcessor struct {
	input  chan int
	output chan int
}

// Process processes items from input channel
func (cp *ChannelProcessor) Process(ctx context.Context) {
	go func() {
		for {
			select {
			case item := <-cp.input:
				// Process item
				cp.output <- item * 2
			case <-ctx.Done():
				return
			}
		}
	}()
}

// Pointer receiver vs value receiver examples
type Counter struct {
	count int
}

// Increment increments counter (pointer receiver)
func (c *Counter) Increment() {
	c.count++
}

// GetCount returns current count (value receiver)
func (c Counter) GetCount() int {
	return c.count
}

// Complex function with multiple defer statements
func ComplexOperation() (result int, err error) {
	defer func() {
		if r := recover(); r != nil {
			err = nil
		}
	}()

	defer func() {
		result++
	}()

	result = 42
	return
}

// Interface with embedded interface
type Reader interface {
	Read() ([]byte, error)
}

type Writer interface {
	Write(data []byte) error
}

type ReadWriter interface {
	Reader
	Writer
	Close() error
}

// Struct with embedded fields
type BaseService struct {
	name string
}

// ExtendedService embeds BaseService
type ExtendedService struct {
	BaseService
	version int
}

// Anonymous function assigned to variable (not typical Go, but testing edge case)
var anonymousFunc = func(x int) int {
	return x * 2
}

// Function returning function
func MakeAdder(x int) func(int) int {
	return func(y int) int {
		return x + y
	}
}

// Type alias
type StringAlias = string

// Blank identifier in parameters
func ProcessWithIgnored(_, y int) int {
	return y
}
