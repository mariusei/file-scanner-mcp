// Edge cases for Swift scanner testing

import Foundation
import Combine

// MARK: - Generics with constraints

/// Generic container with constraints
struct GenericContainer<T: Hashable & Codable> {
    private var items: [T] = []

    mutating func add(_ item: T) {
        items.append(item)
    }

    func get(at index: Int) -> T? {
        guard index >= 0 && index < items.count else { return nil }
        return items[index]
    }
}

/// Generic function with where clause
func compare<T, U>(_ a: T, _ b: U) -> Bool where T: Equatable, U: Equatable, T == U {
    return a == b
}

// MARK: - Protocol extensions with constraints

protocol DataProvider {
    associatedtype DataType
    func fetch() async throws -> DataType
}

extension DataProvider where DataType: Codable {
    func serialize() throws -> Data {
        return try JSONEncoder().encode(fetch() as! DataType)
    }
}

// MARK: - Actors (Swift concurrency)

/// Thread-safe counter using actor
actor Counter {
    private var count: Int = 0

    func increment() {
        count += 1
    }

    func getCount() -> Int {
        return count
    }
}

/// Main actor bound view model
@MainActor
class ViewModel: ObservableObject {
    @Published var data: [String] = []
    @Published private(set) var isLoading = false

    func loadData() async {
        isLoading = true
        // Fetch data
        isLoading = false
    }

    nonisolated func getIdentifier() -> String {
        return "ViewModel"
    }
}

// MARK: - Async/await functions

/// Async function with throws
func fetchData(from url: URL) async throws -> Data {
    let (data, _) = try await URLSession.shared.data(from: url)
    return data
}

/// Async sequence processing
func processItems(_ items: [Int]) async -> [Int] {
    var results: [Int] = []
    for await item in items.async {
        results.append(item * 2)
    }
    return results
}

// MARK: - Property wrappers

@propertyWrapper
struct Clamped<Value: Comparable> {
    private var value: Value
    private let range: ClosedRange<Value>

    var wrappedValue: Value {
        get { value }
        set { value = min(max(newValue, range.lowerBound), range.upperBound) }
    }

    init(wrappedValue: Value, _ range: ClosedRange<Value>) {
        self.range = range
        self.value = min(max(wrappedValue, range.lowerBound), range.upperBound)
    }
}

// MARK: - Result builders

@resultBuilder
struct ArrayBuilder<Element> {
    static func buildBlock(_ components: Element...) -> [Element] {
        return components
    }

    static func buildOptional(_ component: [Element]?) -> [Element] {
        return component ?? []
    }
}

func buildArray<T>(@ArrayBuilder<T> _ content: () -> [T]) -> [T] {
    return content()
}

// MARK: - Opaque return types

protocol Shape {
    func area() -> Double
}

struct Square: Shape {
    var side: Double
    func area() -> Double { side * side }
}

/// Function returning opaque type
func makeShape() -> some Shape {
    return Square(side: 10)
}

// MARK: - Nested types

struct OuterType {
    struct InnerType {
        var value: Int

        enum NestedEnum {
            case first
            case second
        }
    }

    class InnerClass {
        static let shared = InnerClass()
    }
}

// MARK: - Variadic parameters and default values

/// Function with variadic parameters
func printAll(_ items: Any..., separator: String = ", ") {
    print(items.map { String(describing: $0) }.joined(separator: separator))
}

/// Function with default parameter values
func greet(name: String, greeting: String = "Hello", punctuation: String = "!") -> String {
    return "\(greeting), \(name)\(punctuation)"
}

// MARK: - Subscripts

struct Matrix {
    private var grid: [[Int]]
    let rows: Int
    let columns: Int

    init(rows: Int, columns: Int) {
        self.rows = rows
        self.columns = columns
        self.grid = Array(repeating: Array(repeating: 0, count: columns), count: rows)
    }

    subscript(row: Int, column: Int) -> Int {
        get { grid[row][column] }
        set { grid[row][column] = newValue }
    }

    subscript(row: Int) -> [Int] {
        get { grid[row] }
        set { grid[row] = newValue }
    }
}

// MARK: - Static and class methods

class BaseClass {
    static func staticMethod() -> String {
        return "static"
    }

    class func classMethod() -> String {
        return "class"
    }

    final func finalMethod() {
        // Cannot be overridden
    }
}

// MARK: - Inout parameters and mutating methods

struct Point {
    var x: Double
    var y: Double

    mutating func moveBy(dx: Double, dy: Double) {
        x += dx
        y += dy
    }

    nonmutating func distance(to other: Point) -> Double {
        let dx = other.x - x
        let dy = other.y - y
        return (dx * dx + dy * dy).squareRoot()
    }
}

/// Function with inout parameter
func swapValues(_ a: inout Int, _ b: inout Int) {
    let temp = a
    a = b
    b = temp
}

// MARK: - @objc interoperability

@objc class ObjCCompatibleClass: NSObject {
    @objc var name: String = ""

    @objc func performAction() {
        print("Action performed")
    }

    @objc(customSelectorName)
    func methodWithCustomSelector() {
        // Custom Objective-C selector
    }
}

// MARK: - Lazy properties

class LazyExample {
    lazy var expensiveProperty: [Int] = {
        var array: [Int] = []
        for i in 0..<1000 {
            array.append(i)
        }
        return array
    }()
}

// MARK: - Initializers

class InitializerExamples {
    var value: Int

    // Designated initializer
    init(value: Int) {
        self.value = value
    }

    // Convenience initializer
    convenience init() {
        self.init(value: 0)
    }

    // Failable initializer
    init?(string: String) {
        guard let intValue = Int(string) else { return nil }
        self.value = intValue
    }

    // Required initializer
    required init(required: Bool) {
        self.value = required ? 1 : 0
    }
}

// MARK: - Deinit

class ResourceManager {
    init() {
        print("Resource allocated")
    }

    deinit {
        print("Resource deallocated")
    }
}
