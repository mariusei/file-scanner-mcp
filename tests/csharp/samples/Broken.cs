/// <summary>
/// Broken C# file for testing error handling.
/// </summary>

using System;
using System.Collections.Generic

namespace MyApp.Broken
{
    /// <summary>
    /// Missing closing brace for class.
    /// </summary>
    public class BrokenClass
    {
        private string _value;

        public BrokenClass(string value
        {
            _value = value;
        }

        // Missing method body closing brace
        public void BrokenMethod()
        {
            Console.WriteLine("Test");
        // Missing closing brace

        /// Incomplete property
        public string Value
        {
            get => _value
        }

    // Missing class closing brace

    /// Another broken class
    public class AnotherClass {
        public void Method1() {
        }

        // Unclosed method
        public void BrokenMethod2() {
            if (true) {
                Console.WriteLine("test")
            }
    }

    // Syntax errors
    public interface IBroken
        string Property { get; set;
        void Method(;
    }

    // Malformed enum
    public enum BrokenEnum
    {
        Value1,
        Value2
        Value3,
    }

    public struct BrokenStruct
        int X;
        int Y;
    }
}
