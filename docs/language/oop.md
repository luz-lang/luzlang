# Object-Oriented Programming

## Defining a class

```
class Animal {
    function init(self, name) {
        self.name = name
    }

    function speak(self) {
        write($"{self.name} makes a sound")
    }
}
```

- `init` is the constructor. It is called automatically when the class is instantiated.
- `self` refers to the current instance and must be the first parameter of every method.
- Attributes are created by assigning to `self.attribute_name`.

## Creating instances

```
a = Animal("Leo")
a.speak()          # Leo makes a sound
write(a.name)      # Leo
```

## Attributes

Attributes can be set on instances at any time:

```
a.age = 5
write(a.age)   # 5
```

## Inheritance

Use `extends` to inherit from a parent class. The child class automatically inherits all parent methods.

```
class Dog extends Animal {
    function init(self, name, breed) {
        super.init(name)
        self.breed = breed
    }

    function speak(self) {
        super.speak()
        write("(woof!)")
    }
}

d = Dog("Rex", "Labrador")
d.speak()
# Rex makes a sound
# (woof!)
```

## super

`super` gives access to the parent class's methods from inside a child method. Call parent methods with `super.method_name(args)`.

```
class Cat extends Animal {
    function speak(self) {
        super.speak()   # calls Animal.speak
        write("(meow!)")
    }
}
```

## Method overriding

Defining a method with the same name in a child class replaces the parent's version:

```
class GuideDog extends Dog {
    function speak(self) {
        write($"{self.name} is a guide dog and stays quiet.")
    }
}

g = GuideDog("Buddy", "Retriever")
g.speak()   # Buddy is a guide dog and stays quiet.
```

## instanceof

`instanceof(obj, Class)` returns `true` if `obj` is an instance of `Class` or any of its subclasses. It walks the full inheritance hierarchy:

```
write(instanceof(d, Dog))     # true
write(instanceof(d, Animal))  # true  (Dog extends Animal)
write(instanceof(d, Cat))     # false
```

## typeof

`typeof(value)` returns the type name as a string. For class instances it returns the class name:

```
write(typeof(d))    # Dog
write(typeof(42))   # int
```

## Bound methods

When you retrieve a method from an instance, `self` is automatically bound to it. You can store the method in a variable and call it later without passing the instance:

```
class Counter {
    function init(self) { self.n = 0 }
    function inc(self) {
        self.n = self.n + 1
        return self.n
    }
}

c = Counter()
inc = c.inc   # bound method — self is already c

write(inc())  # 1
write(inc())  # 2
write(inc())  # 3
```

This works with any method, including inherited ones. The bound method always refers to the original instance.

## Polymorphism

Because Luz is dynamically typed, any object with the right methods can be used interchangeably:

```
class Shape {
    function area(self) { return 0 }
}

class Circle extends Shape {
    function init(self, r) { self.r = r }
    function area(self) { return self.r * self.r * 3 }
}

class Rectangle extends Shape {
    function init(self, w, h) { self.w = w   self.h = h }
    function area(self) { return self.w * self.h }
}

shapes = [Circle(5), Rectangle(4, 6)]
for shape in shapes {
    write(shape.area())
}
# 75
# 24
```
