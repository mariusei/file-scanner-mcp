/// <summary>
/// Edge cases for C# scanner testing.
/// </summary>

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

namespace MyApp.Advanced
{
    /// <summary>
    /// Generic container class.
    /// </summary>
    public class GenericContainer<T> where T : class
    {
        private T _value;

        /// <summary>
        /// Gets or sets the contained value.
        /// </summary>
        public T Value { get; set; }

        /// <summary>
        /// Process items with complex generic signature.
        /// </summary>
        public async Task<List<T>> ProcessAsync<TResult>(
            IEnumerable<T> items,
            Func<T, TResult> mapper,
            Predicate<TResult> filter)
        {
            await Task.Delay(100);
            return new List<T>();
        }
    }

    /// <summary>
    /// Generic key-value store.
    /// </summary>
    public class KeyValueStore<TKey, TValue>
        where TKey : IComparable<TKey>
        where TValue : class, new()
    {
        private Dictionary<TKey, TValue> _store = new Dictionary<TKey, TValue>();

        /// <summary>
        /// Adds an item to the store.
        /// </summary>
        public void Add(TKey key, TValue value)
        {
            _store[key] = value;
        }

        /// <summary>
        /// Retrieves a value by key.
        /// </summary>
        public TValue? Get(TKey key)
        {
            return _store.TryGetValue(key, out var value) ? value : null;
        }
    }

    /// <summary>
    /// Demonstrates various attributes.
    /// </summary>
    [Serializable]
    [Obsolete("Use NewAnnotationShowcase instead")]
    public class AnnotationShowcase
    {
        /// <summary>
        /// A deprecated method.
        /// </summary>
        [Deprecated]
        [Obsolete("Use NewMethod instead", true)]
        public void OldMethod()
        {
            Console.WriteLine("Old method");
        }

        /// <summary>
        /// Override of ToString.
        /// </summary>
        public override string ToString()
        {
            return "AnnotationShowcase";
        }

        /// <summary>
        /// Method with multiple attributes.
        /// </summary>
        [System.Runtime.CompilerServices.MethodImpl(
            System.Runtime.CompilerServices.MethodImplOptions.AggressiveInlining)]
        [System.Diagnostics.DebuggerStepThrough]
        private void ComplexAttributes()
        {
        }
    }

    /// <summary>
    /// Abstract base service class.
    /// </summary>
    public abstract class AbstractService
    {
        /// <summary>
        /// Abstract method to be implemented.
        /// </summary>
        public abstract void Execute();

        /// <summary>
        /// Virtual method that can be overridden.
        /// </summary>
        public virtual void Initialize()
        {
            Console.WriteLine("Initializing");
        }
    }

    /// <summary>
    /// Concrete implementation of AbstractService.
    /// </summary>
    public class ConcreteService : AbstractService
    {
        /// <summary>
        /// Implementation of Execute.
        /// </summary>
        public override void Execute()
        {
            Console.WriteLine("Executing");
        }

        /// <summary>
        /// Override of Initialize.
        /// </summary>
        public override void Initialize()
        {
            base.Initialize();
            Console.WriteLine("ConcreteService initialized");
        }
    }

    /// <summary>
    /// Outer class with nested classes.
    /// </summary>
    public class OuterClass
    {
        /// <summary>
        /// Inner class.
        /// </summary>
        public class InnerClass
        {
            public void InnerMethod()
            {
                Console.WriteLine("Inner method");
            }
        }

        /// <summary>
        /// Static nested class.
        /// </summary>
        public static class StaticNestedClass
        {
            public static void StaticMethod()
            {
                Console.WriteLine("Static method");
            }
        }

        /// <summary>
        /// Private nested struct.
        /// </summary>
        private struct PrivateStruct
        {
            public int Value { get; set; }
        }
    }

    /// <summary>
    /// User role enumeration with explicit base type.
    /// </summary>
    public enum Status : byte
    {
        Pending = 0,
        Active = 1,
        Inactive = 2,
        Deleted = 3
    }

    /// <summary>
    /// Demonstrates async/await patterns.
    /// </summary>
    public class AsyncExample
    {
        /// <summary>
        /// Async method returning Task.
        /// </summary>
        public async Task FetchDataAsync()
        {
            await Task.Delay(1000);
        }

        /// <summary>
        /// Async method returning Task with value.
        /// </summary>
        public async Task<string> GetMessageAsync()
        {
            await Task.Delay(100);
            return "Hello";
        }

        /// <summary>
        /// Async method with cancellation token.
        /// </summary>
        public async Task ProcessAsync(System.Threading.CancellationToken cancellationToken)
        {
            await Task.Delay(500, cancellationToken);
        }
    }

    /// <summary>
    /// Demonstrates LINQ and lambda expressions.
    /// </summary>
    public class LinqExample
    {
        /// <summary>
        /// Transform data using LINQ.
        /// </summary>
        public List<int> TransformData(
            List<string> input,
            Func<string, int> mapper,
            Func<int, bool> filter)
        {
            return input
                .Select(mapper)
                .Where(filter)
                .OrderBy(x => x)
                .ToList();
        }

        /// <summary>
        /// Query with multiple clauses.
        /// </summary>
        public IEnumerable<string> ComplexQuery(List<int> numbers)
        {
            var query = from n in numbers
                        where n > 10
                        orderby n descending
                        select n.ToString();
            return query;
        }
    }

    /// <summary>
    /// Interface with properties and methods.
    /// </summary>
    public interface IRepository<T> where T : class
    {
        /// <summary>
        /// Gets all items.
        /// </summary>
        Task<IEnumerable<T>> GetAllAsync();

        /// <summary>
        /// Gets item by ID.
        /// </summary>
        Task<T?> GetByIdAsync(int id);

        /// <summary>
        /// Adds a new item.
        /// </summary>
        Task AddAsync(T item);

        /// <summary>
        /// Count property.
        /// </summary>
        int Count { get; }
    }

    /// <summary>
    /// Readonly struct for performance.
    /// </summary>
    public readonly struct Vector3
    {
        public double X { get; }
        public double Y { get; }
        public double Z { get; }

        public Vector3(double x, double y, double z)
        {
            X = x;
            Y = y;
            Z = z;
        }

        /// <summary>
        /// Calculate magnitude.
        /// </summary>
        public double Magnitude() => Math.Sqrt(X * X + Y * Y + Z * Z);
    }

    /// <summary>
    /// Record type for immutable data.
    /// </summary>
    public record Person(string FirstName, string LastName, int Age);

    /// <summary>
    /// Record with methods.
    /// </summary>
    public record Company(string Name, string Industry)
    {
        /// <summary>
        /// Gets the full description.
        /// </summary>
        public string GetDescription() => $"{Name} - {Industry}";
    }

    /// <summary>
    /// Sealed class to prevent inheritance.
    /// </summary>
    public sealed class SealedService
    {
        public void DoWork()
        {
            Console.WriteLine("Working");
        }
    }

    /// <summary>
    /// Static class with extension methods.
    /// </summary>
    public static class StringExtensions
    {
        /// <summary>
        /// Extension method for string.
        /// </summary>
        public static bool IsNullOrEmpty(this string value)
        {
            return string.IsNullOrEmpty(value);
        }

        /// <summary>
        /// Another extension method.
        /// </summary>
        public static string Reverse(this string value)
        {
            return new string(value.Reverse().ToArray());
        }
    }
}
