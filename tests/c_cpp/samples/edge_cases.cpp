// Edge cases for C++ scanner testing

#include <iostream>
#include <string>
#include <memory>
#include <vector>
#include <map>

// Template class with multiple type parameters
template<typename K, typename V>
class KeyValueStore {
private:
    std::map<K, V> storage;

public:
    // Insert key-value pair
    void insert(const K& key, const V& value) {
        storage[key] = value;
    }

    // Get value by key
    V get(const K& key) const {
        auto it = storage.find(key);
        if (it != storage.end()) {
            return it->second;
        }
        return V();
    }

    // Check if key exists
    bool contains(const K& key) const {
        return storage.find(key) != storage.end();
    }
};

// Template specialization
template<>
class KeyValueStore<std::string, int> {
public:
    void insert(const std::string& key, const int& value) {
        std::cout << "Specialized insert: " << key << " = " << value << std::endl;
    }
};

// Class with operator overloading
class Complex {
private:
    double real;
    double imag;

public:
    // Constructor
    Complex(double r = 0.0, double i = 0.0) : real(r), imag(i) {}

    // Operator overloading: addition
    Complex operator+(const Complex& other) const {
        return Complex(real + other.real, imag + other.imag);
    }

    // Operator overloading: multiplication
    Complex operator*(const Complex& other) const {
        return Complex(
            real * other.real - imag * other.imag,
            real * other.imag + imag * other.real
        );
    }

    // Operator overloading: equality
    bool operator==(const Complex& other) const {
        return real == other.real && imag == other.imag;
    }

    // Operator overloading: stream output
    friend std::ostream& operator<<(std::ostream& os, const Complex& c) {
        os << c.real << " + " << c.imag << "i";
        return os;
    }

    // Conversion operator
    operator double() const {
        return real;
    }
};

// Class with const methods
class DataCache {
private:
    mutable std::map<std::string, std::string> cache;
    int access_count;

public:
    DataCache() : access_count(0) {}

    // Const method that modifies mutable member
    std::string get(const std::string& key) const {
        access_count++;  // Would fail without mutable
        auto it = cache.find(key);
        return it != cache.end() ? it->second : "";
    }

    // Const method
    int get_access_count() const {
        return access_count;
    }

    // Non-const method
    void set(const std::string& key, const std::string& value) {
        cache[key] = value;
    }
};

// Class with virtual methods and pure virtual (abstract)
class Shape {
public:
    virtual ~Shape() = default;

    // Pure virtual method
    virtual double area() const = 0;

    // Virtual method with implementation
    virtual void draw() const {
        std::cout << "Drawing shape" << std::endl;
    }

    // Non-virtual method
    void info() const {
        std::cout << "Shape info" << std::endl;
    }
};

// Derived class
class Circle : public Shape {
private:
    double radius;

public:
    Circle(double r) : radius(r) {}

    // Override pure virtual
    double area() const override {
        return 3.14159 * radius * radius;
    }

    // Override virtual method
    void draw() const override {
        std::cout << "Drawing circle" << std::endl;
    }
};

// Class with static members
class Counter {
private:
    static int instance_count;
    int id;

public:
    Counter() : id(++instance_count) {}

    // Static method
    static int get_instance_count() {
        return instance_count;
    }

    // Inline method
    inline int get_id() const { return id; }
};

// Initialize static member
int Counter::instance_count = 0;

// Nested namespace
namespace outer {
namespace inner {

// Class in nested namespace
class NestedClass {
public:
    void do_something() {
        std::cout << "Nested class method" << std::endl;
    }
};

} // namespace inner
} // namespace outer

// C++11 attribute
[[nodiscard]] bool validate_input(const std::string& input) {
    return !input.empty();
}

// Deleted and defaulted functions
class NonCopyable {
public:
    NonCopyable() = default;
    NonCopyable(const NonCopyable&) = delete;
    NonCopyable& operator=(const NonCopyable&) = delete;
    NonCopyable(NonCopyable&&) = default;
    NonCopyable& operator=(NonCopyable&&) = default;
};

// Variadic template function
template<typename... Args>
void print_all(Args... args) {
    (std::cout << ... << args) << std::endl;
}

// Lambda and auto
void lambda_example() {
    auto add = [](int a, int b) -> int {
        return a + b;
    };

    auto result = add(5, 3);
    std::cout << "Result: " << result << std::endl;
}

// Constexpr function
constexpr int factorial(int n) {
    return n <= 1 ? 1 : n * factorial(n - 1);
}

// Anonymous namespace
namespace {
    void internal_helper() {
        std::cout << "Internal helper" << std::endl;
    }
}

// Friend class
class AccessController {
private:
    int secret_value;

    // Friend class declaration
    friend class Accessor;

public:
    AccessController() : secret_value(42) {}
};

class Accessor {
public:
    int get_secret(const AccessController& ac) {
        return ac.secret_value;
    }
};

// Main function
int main() {
    // Test template class
    KeyValueStore<std::string, int> store;
    store.insert("age", 25);

    // Test operator overloading
    Complex c1(1.0, 2.0);
    Complex c2(3.0, 4.0);
    Complex c3 = c1 + c2;

    // Test const methods
    DataCache cache;
    cache.set("key1", "value1");
    std::string val = cache.get("key1");

    // Test virtual methods
    Circle circle(5.0);
    circle.draw();
    std::cout << "Area: " << circle.area() << std::endl;

    // Test static methods
    std::cout << "Instances: " << Counter::get_instance_count() << std::endl;

    // Test constexpr
    constexpr int fact5 = factorial(5);
    std::cout << "5! = " << fact5 << std::endl;

    return 0;
}
