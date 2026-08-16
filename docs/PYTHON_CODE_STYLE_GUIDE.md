# Google Python 风格指南（中文版）

> 来源：[`zh-google-styleguide/zh-google-styleguide`](https://github.com/zh-google-styleguide/zh-google-styleguide/tree/c1f8ac9138bce1b829fdffcfa03e8df44584ef22/google-python-styleguide)  
> 上游版本：`c1f8ac9138bce1b829fdffcfa03e8df44584ef22`  
> 获取与转换日期：2026-08-15  
> 许可：Apache License 2.0
>
> 本文件是开源中文原稿的格式转换版本。为便于在本项目和 GitHub 中直接阅读，
> 已将上游 reStructuredText 文件合并并机械转换为 Markdown；正文规则未按
> rewater-agent 业务进行增删。格式转换可能造成少量锚点或嵌套列表差异，
> 规则含义有疑问时以上游原稿为准。

## 背景

Python 是谷歌使用的重要动态语言。这本风格指南列举了 Python 程序应采纳和避免的风格。

为帮助你正确地格式化代码，我们创建了 [Vim的配置文件  ](https://github.com/google/styleguide/blob/gh-pages/google_python_style.vim) 。对于Emacs用户，保持默认设置即可。

许多团队采用 [Black ](https://github.com/psf/black) 和 [Pyink ](https://github.com/google/pyink) 作为自动格式化工具,以避免格式上的争论。

## Python语言规范

### Lint

> **提示：**
> 用 [pylintrc ](https://google.github.io/styleguide/pylintrc) 运行 pylint, 以检查你的代码.

定义:
pylint 是在 Python 代码中寻找 bug 和格式问题的工具. 它寻找的问题就像 C 和 C++ 这些更静态的(译者注: 原文是less dynamic)语言中编译器捕捉的问题. 出于Python的动态特性, 部分警告可能有误. 不过, 误报应该不常见.

优点:
可以发现疏忽, 例如拼写错误, 使用未赋值的变量等.

缺点:
pylint 不完美. 要利用其优势, 我们有时侯需要: a) 绕过它 b) 抑制它的警告 或者 c) 改进它.

结论:
一定要用pylint检查你的代码.

抑制不恰当的警告, 以免其他问题被警告淹没。你可以用行注释来抑制警告. 例如:

```python
def do_PUT(self):  # WSGI 接口名, 所以 pylint: disable=invalid-name
    ...
```

pylint的警告均以符号名(如 `empty-docstring` )来区分. 谷歌特有的警告以 `g-` 为前缀.

如果警告的符号名不够见名知意，那么请添加注释。

这种抑制方式的好处是, 我们可以轻易搜索并重新评判这些注释.

你可以用命令 `pylint --list-msgs` 来列出 pylint 的所有警告. 你可以用命令 `pylint --help-msg=invalid-name`  来查询某个警告的详情.

相较于旧的格式 `pylint: disable-msg` , 本文推荐使用 `pylint: disable` .

如果有“参数未使用”的警告，你可以在函数体开头删除无用的变量，以消除警告. 一定要用注释说明你为什么删除这些变量. 注明"未使用."即可. 例如:

```python
def viking_cafe_order(spam: str, beans: str, eggs: str | None = None) -> str:
    del beans, eggs  # 未被维京人使用.
    return spam + spam + spam
```

(译者注：Viking 意为维京人.)

其他避免这种警告的常用方法还有: 用`_`作为未使用参数的名称; 给这些参数名加上前缀 `unused_`; 或者把它们赋值给变量 `_`. 我们允许但是不再推荐这些方法. 这会导致调用者无法通过参数名来传参，也不能保证变量确实没被引用。

### 导入

> **提示：**
> 使用 `import` 语句时, 只导入包和模块, 而不单独导入函数或者类。

定义:
用于方便模块间共享代码的重用机制.

优点:
命名空间的管理规范十分简单. 每个标识符的来源都用一致的方式来表示. `x.Obj` 表示 `Obj` 对象定义在模块 `x` 中.

缺点:
模块名可能有命名冲突. 有些模块名的长度过长以至于不方便.

结论:
1. 用 `import x` 来导入包和模块.

1. 用 `from x import y` , 其中x是包前缀, y是不带前缀的模块名.

1. 在以下情况使用 `from x import y as z`: 如果有两个模块都叫 `y`; 如果 `y` 和当前模块的某个全局名称冲突; 如果 `y` 是长度过长的名称.

1. 仅当缩写 `z` 是标准缩写时才能使用 `import y as z`.(比如 `np` 代表 `numpy`.)

例如, 可以用如下方式导入模块 `sound.effects.echo`:

```python
from sound.effects import echo
...
echo.EchoFilter(input, output, delay=0.7, atten=4)
```

导入时禁止使用相对包名. 即使模块在同一个包中, 也要使用完整包名. 这能避免无意间重复导入同一个包.

例外:

这一规定的例外是：

1. 以下用于静态分析和类型检查的模块:

    1. `typing` 模块
    1. `collections.abc` 模块
    1. `typing_extensions` 模块

1. [six.moves ](https://six.readthedocs.io/#module-six.moves) 模块中的重定向.

### 包

> **提示：**
> 使用每个模块的完整路径名来导入模块.

优点:
避免模块名冲突, 或是因模块搜索路径与作者的想法不符而导入错误的包. 也更容易找到模块.

缺点:
部署代码更难, 因为你必须完整复刻包的层次. 在现代的部署模式下不再是问题.

结论:
所有新的代码都应该用完整包名来导入每个模块.

应该像下面这样导入:

正确:

```python
# 在代码中引用完整名称 absl.flags (详细版).
import absl.flags
from doctor.who import jodie

_FOO = absl.flags.DEFINE_string(...)
```

```python
# 在代码中仅引用模块名 flags (常见情况).
from absl import flags
from doctor.who import jodie

_FOO = flags.DEFINE_string(...)
```

错误: (假设当前文件和 `jodie.py` 都在目录 `doctor/who/` 下)

```python
# 没有清晰地表达作者想要导入的模块和最终导入的模块.
# 实际导入的模块取决于由外部环境控制的 sys.path.
# 那些名为 jodie 的模块中, 哪个才是作者想导入的?
import jodie
```

不能臆测 `sys.path` 包含主程序所在的目录, 即使这种环境的确存在. 因此, 代码必须认定 `import jodie` 表示的是名为 `jodie` 的第三方库或者顶层的包，而非当前目录的 `jodie.py`.

### 异常

> **提示：**
> 允许使用异常, 但必须谨慎使用.

定义:
异常是一种跳出正常的控制流, 以处理错误或其它异常情况的方法.

优点:
处理正常情况的控制流不会和错误处理代码混在一起. 在特定情况下, 它也能让控制流跳出多层调用帧. 例如, 一步跳出N多层嵌套的函数, 而不必逐层传递错误代码.

缺点:
可能导致控制流晦涩难懂. 调用库函数时容易忘记处理异常.

结论:
使用异常时必须遵守特定要求:

1. 优先使用合适的内置异常类. 比如, 用 `ValueError` 表示前置条件错误 (例如给必须为正数的参数传入了负值). 不要使用 `assert` 语句来验证公开API的参数值. 应该用 `assert` 来保证内部正确性, 不应该用 `assert` 来纠正参数或表示意外情况. 若要用异常来表示意外情况, 应该用 `raise`. 例如:

    正确:

```python
def connect_to_next_port(self, minimum: int) -> int:
    """连接到下一个可用的端口.

    参数:
        minimum: 一个大于等于 1024 的端口号.

    返回:
        新的最小端口.

    抛出:
        ConnectionError: 没有可用的端口.
    """
    if minimum < 1024:
        # 注意这里抛出 ValueError 的情况没有在文档里说明，因为 API 的
        # 错误用法应该是未定义行为.
        raise ValueError(f'最小端口号至少为 1024，不能是 {minimum}.')
    port = self._find_next_open_port(minimum)
    if port is None:
        raise ConnectionError(
            f'未能通过 {minimum} 或更高的端口号连接到服务.')
    assert port >= minimum, (
        f'意外的端口号 {port}, 端口号不应小于 {minimum}.')
    return port
```

    错误:

```python
def connect_to_next_port(self, minimum: int) -> int:
    """连接到下一个可用的端口.

    参数:
        minimum: 一个大于等于 1024 的端口号.

    返回:
        新的最小端口.
    """
    assert minimum >= 1024, '最小端口号至少为 1024.'
    port = self._find_next_open_port(minimum)
    assert port is not None
    return port
```

1. 模块或包可以定义自己的异常类型, 这些类必须继承已有的异常类. 异常类型名应该以 `Error` 为后缀, 并且不应该有重复 (例如 `foo.FooError`).
1. 永远不要使用 `except:` 语句来捕获所有异常, 也不要捕获 `Exception` 或者 `StandardError` , 除非你想:

    1. 重新抛出异常.
    1. 在程序中创造一个隔离点, 记录并抑制异常, 让异常不再继续传播. 这种写法可以用在线程的最外层, 以避免程序崩溃.

    如果你使用这种写法, Python 将非常宽容. `except:` 真的会捕获任何错误, 包括拼写错误的符号名、 `sys.exit()` 调用、 `Ctrl+C` 中断、单元测试错误和各种你不想捕获的错误.

1. 最小化 `try/except` 代码块中的代码量. `try` 的范围越大, 就越容易把你没想到的那些能抛出异常的代码囊括在内. 这样的话, `try/except` 代码块就掩盖了真正的错误.
1. 用 `finally` 表示无论异常与否都应执行的代码. 这种写法常用于清理资源, 例如关闭文件.

### 全局变量

> **提示：**
> 避免全局变量.

定义:
在程序运行时可以发生变化的模块级变量和类属性 (class attribute).

优点:
偶尔有用.

缺点:
1. 破坏封装: 这种设计会阻碍一些有用的目标. 例如, 如果用全局变量来管理数据库连接, 那就难以同时连接两个数据库 (比如为了在数据迁移时比较差异). 全局注册表也有类似的问题.
1. 导入模块时可能改变模块的行为, 因为首次导入模块时会对全局变量赋值.

结论:
避免使用全局变量.

在特殊情况下需要用到全局变量时, 应将全局变量声明为模块级变量或者类属性, 并在名称前加 `_` 以示为内部状态. 如需从外部访问全局变量, 必须通过公有函数或类方法实现. 详见 [命名规则 ](https://google.github.io/styleguide/pyguide.html#s3.16-naming) 章节. 请用注释或文档链接解释这些全局变量的设计思想.

我们允许并鼓励使用模块级常量,例如 `_MAX_HOLY_HANDGRENADE_COUNT = 3` 表示内部常量, `SIR_LANCELOTS_FAVORITE_COLOR = "blue"` 表示公开API的常量. 注意常量名必须全部大写, 用下划线分隔单词. 详见 [命名规则 ](https://google.github.io/styleguide/pyguide.html#s3.16-naming) 章节.

### 嵌套/局部/内部类和函数

> **提示：**
> 可以用局部类和局部函数来捕获局部变量. 可以用内部类.

定义:
可以在方法、函数和类中定义内部类. 可以在方法和函数中定义嵌套函数. 嵌套函数可以只读访问外层作用域中的变量. (译者注:即内嵌函数可以读外部函数中定义的变量,但是无法改写,除非使用 `nonlocal`)

优点:
方便定义作用域有限的工具类和函数. 便于实现 [抽象数据类型 ](https://en.wikipedia.org/wiki/Abstract_data_type). 常用于实现装饰器.

缺点:
无法直接测试嵌套的函数和类. 嵌套函数和嵌套类会让外层函数的代码膨胀, 可读性变差.

结论:
可以谨慎使用. 尽量避免使用嵌套函数和嵌套类, 除非需要捕获 `self` 和 `cls` 以外的局部变量. 不要仅仅为了隐藏一个函数而使用嵌套函数. 应将需要隐藏的函数定义在模块级别, 并给名称加上 `_` 前缀, 以便在测试代码中调用此函数.

### 推导式 (comprehension expression) 和生成式 (generator expression)

> **提示：**
> 适用于简单情况.

定义:
列表、字典和集合的推导式和生成式可以用于简洁高效地创建容器和迭代器, 而无需借助循环、 `map()`、 `filter()`, 或者 `lambda` . (译者注: 元组是没有推导式的, `()` 内加类似推导式的句式返回的是个生成器)

优点:
相较于其它创建字典、列表和集合的方法, 简单的列表推导式更加清晰和简洁. 生成器表达式十分高效, 因为无需创建整个列表.

缺点:
复杂的列表推导式和生成式难以理解.

结论:
可以用于简单情况. 以下每个部分不应超过一行: 映射表达式、for语句和过滤表达式. 禁止多重for语句和多层过滤. 情况复杂时, 应该用循环.

正确:

```python
result = [mapping_expr for value in iterable if filter_expr]

result = [{'key': value} for value in iterable
          if a_long_filter_expression(value)]

result = [complicated_transform(x)
          for x in iterable if predicate(x)]

descriptive_name = [
    transform({'key': key, 'value': value}, color='black')
    for key, value in generate_iterable(some_input)
    if complicated_condition_is_met(key, value)
]

result = []
for x in range(10):
    for y in range(5):
        if x * y > 10:
            result.append((x, y))

return {x: complicated_transform(x)
        for x in long_generator_function(parameter)
        if x is not None}

squares_generator = (x**2 for x in range(10))

unique_names = {user.name for user in users if user is not None}

eat(jelly_bean for jelly_bean in jelly_beans
    if jelly_bean.color == 'black')
```

错误:

```python
result = [complicated_transform(
              x, some_argument=x+1)
          for x in iterable if predicate(x)]

result = [(x, y) for x in range(10) for y in range(5) if x * y > 10]

return ((x, y, z)
        for x in xrange(5)
        for y in xrange(5)
        if x != y
        for z in xrange(5)
        if y != z)
```

### 默认迭代器和操作符

> **提示：**
> 只要可行, 就用列表、字典和文件等类型的默认迭代器和操作符.

定义:
字典和列表等容器类型具有默认的迭代器和关系运算符 ( `in` 和 `not in` ).

优点:
默认迭代器和操作符简单高效. 这种写法可以直白地表达运算, 无需调用额外的函数. 使用默认操作符的函数是泛型函数, 可以用于任何支持该操作符的类型.

缺点:
你不能通过方法名来辨别对象的类型 (除非变量有类型注解). 不过这也是优点.

结论:
只要是支持的类型 (例如列表、字典和文件), 就使用默认迭代器和操作符. 内置类型也定义了一些返回迭代器的方法. 优先使用返回迭代器的方法, 而非返回列表的方法, 不过注意使用迭代器时不能修改容器.

正确:

```python
for key in adict: ...
if obj in alist: ...
for line in afile: ...
for k, v in adict.items(): ...
```

错误:

```python
for key in adict.keys(): ...
for line in afile.readlines(): ...
```

### 生成器

> **提示：**
> 按需使用生成器.

定义:
生成器函数会返回一个迭代器. 每当函数执行 `yield` 语句时, 迭代器就生成一个值. 随后, 生成器的运行状态将暂停, 直到需要下一个值的时候.

优点:
代码简单, 因为生成器可以保存局部变量和控制流. 相较于直接创建整个列表的函数, 生成器使用的内存更少.

缺点:
必须等到生成结束或者生成器本身被内存回收的时候, 生成器的局部变量才能被内存回收.

结论:
可以使用. 生成器的文档字符串中应使用"Yields:"而不是"Returns:".

(译者注: 参看 注释 )

如果生成器占用了大量资源, 一定要强制清理资源.

一种清理资源的好方法是用上下文管理器包裹生成器 [PEP-0533 ](https://peps.python.org/pep-0533/).

### Lambda函数

> **提示：**
> 适用于单行函数. 建议用生成式替代 `map()/filter()` 与 `lambda` 的组合.

定义:
lambda 定义匿名函数, 不像语句那样定义具名函数.

优点:
方便.

缺点:
比局部函数更难理解和调试. 缺失函数名会导致调用栈晦涩难懂. 由于 lambda 函数只能包含一个表达式, 因此其表达能力有限.

结论:
适用于单行函数. 如果函数体超过60-80个字符, 最好还是定义为常规的嵌套函数.

对于乘法等常见操作, 应该用 `operator` 模块中的函数代替lambda函数. 例如, 推荐用 `operator.mul` 代替 `lambda x, y: x * y` .

### 条件表达式

> **提示：**
> 适用于简单情况.

定义:
条件表达式(又名三元运算符)是if语句的缩略版. 例如: `x = 1 if cond else 2` .

优点:
比if语句更简短, 更方便.

缺点:
有时比if语句更难理解. 如果表达式很长，就难以一眼望到条件.

结论:
适用于简单情况. 以下每部分均不得长于一行: 真值分支, if 部分和 else 部分. 情况复杂时应使用完整的if语句.

正确:

```python
one_line = 'yes' if predicate(value) else 'no'
slightly_split = ('yes' if predicate(value)
                  else 'no, nein, nyet')
the_longest_ternary_style_that_can_be_done = (
    'yes, true, affirmative, confirmed, correct'
    if predicate(value)
    else 'no, false, negative, nay')
```

错误:

```python
bad_line_breaking = ('yes' if predicate(value) else
                     'no')  # 换行位置错误
portion_too_long = ('yes'
                    if some_long_module.some_long_predicate_function(
                        really_long_variable_name)
                    else 'no, false, negative, nay')   # 过长
```

### 默认参数值

> **提示：**
> 大部分情况下允许.

定义:
你可以为参数列表的最后几个参数赋予默认值, 例如, `def foo(a, b = 0):` . 如果调用foo时只带一个参数, 则b为0. 如果调用时带两个参数, 则b的值等于第二个参数.

优点:
很多时候, 你需要一个拥有大量默认值的函数, 并且偶尔需要覆盖这些默认值. 通过默认参数值可以轻松实现这种功能, 不需要为了覆盖默认值而编写大量额外的函数. 同时, Python不支持重载方法和函数, 而默认参数的写法可以轻松"仿造"重载行为.

缺点:
默认参数在模块被导入时求值且只计算一次. 如果值是列表和字典等可变类型, 就可能引发问题. 如果函数修改了这个值(例如往列表内添加元素), 默认值就变化了.

结论:
可以使用, 不过有如下注意事项:

函数和方法的默认值不能是可变 (mutable) 对象.

正确:

```python
def foo(a, b=None):
    if b is None:
        b = []
def foo(a, b: Optional[Sequence] = None):
    if b is None:
        b = []
def foo(a, b: Sequence = ()):  # 允许空元组，因为元组是不可变的
```

错误:

```python
from absl import flags
_FOO = flags.DEFINE_string(...)

def foo(a, b=[]):
    ...
def foo(a, b=time.time()):  # 确定要用模块的导入时间吗???
    ...
def foo(a, b=_FOO.value):  # 此时还没有解析 sys.argv...
    ...
def foo(a, b: Mapping = {}):  # 可能会赋值给未经过静态检查 (unchecked) 的代码
    ...
```

### 特性 (properties)

(译者注:参照fluent python.这里将 "property" 译为"特性",而 "attribute" 译为属性. python中数据的属性和处理数据的方法统称属性"(arrtibute)", 而在不改变类接口的前提下用来修改数据属性的存取方法我们称为"特性(property)".)

> **提示：**
> 可以用特性来读取或设置涉及简单计算、逻辑的属性. 特性的实现必须和属性 (attribute) 一样满足这些通用要求: 轻量、直白、明确.

定义:
把读取、设置属性的函数包装为常规属性操作的写法.

优点:
1. 可以直接实现属性的访问、赋值接口, 而不必添加获取器 (getter) 和设置器 (setter).
1. 可以让属性变为只读.
1. 可以实现惰性求值.
1. 类的内部实现发生变化时, 可以用这种方法让用户看到的公开接口保持不变.

缺点:
1. 可能掩盖副作用, 类似运算符重载 (operator overload).
1. 子类继承时可能产生困惑.

结论:
允许使用特性. 但是, 和运算符重载一样, 只能在必要时使用, 并且要模仿常规属性的存取特点. 若无法满足要求, 请参考 获取器和写入器  的规则.

举个例子, 一个特性不能仅仅用于获取和设置一个内部属性: 因为不涉及计算, 没有必要用特性 (应该把该属性设为公有). 而用特性来限制属性的访问或者计算 **简单** 的衍生值则是正确的: 这种逻辑简单明了.

应该用 `@property` [装饰器 (decorator) ](https://google-styleguide.googlecode.com/svn/trunk/pyguide.html#Function_and_Method_Decorators) 来创建特性. 自行实现的特性装饰器属于威力过大的功能.

特性的继承机制难以理解. 不要用特性实现子类能覆写 (override) 或扩展的计算功能.

### True/False的求值

> **提示：**
> 尽可能使用"隐式"假值.

定义:
Python在计算布尔值时会把一些值视为 `False`. 简单来说, 所有的"空"值都是假值. 因此, `0, None, [], {}, ""` 作为布尔值使用时相当于 `False`.

优点:
Python布尔值可以让条件语句更易懂, 减少失误. 多数时候运行速度也更快.

缺点:
对C/C++开发人员来说, 可能看起来有点怪.

结论:
尽可能使用"隐式"假值, 例如: 使用 `if foo:` 而非 `if foo != []:` . 不过还是有一些注意事项需要你铭记在心:

1. 一定要用 `if foo is None:` (或者 `is not None`) 来检测 `None` 值. 例如, 如果你要检查某个默认值为 `None` 的参数有没有被调用者覆盖, 覆盖的值在布尔语义下可能也是假值!
1. 永远不要用 `==` 比较一个布尔值是否等于 `False`. 应该用 `if not x:` 代替. 如果你需要区分 `False` 和 `None`, 你应该用复合表达式, 例如 `if not x and x is not None:`.
1. 多利用空序列(字符串, 列表, 元组)是假值的特点. 因此 `if not seq:`  比 `if len(seq):` 更好, `if not seq:` 比 `if not len(seq):` 更好.
1. 处理整数时, 使用隐式 False 可能会得不偿失(例如不小心将 `None` 当做0来处理). 你可以显式比较整型值与0的关系 (`len()` 的返回值例外).

    正确:

```python
if not users:
    print('无用户')

if i % 10 == 0:
    self.handle_multiple_of_ten()

def f(x=None):
    if x is None:
        x = []
```

    错误:

```python
if len(users) == 0:
    print '无用户'

if not i % 10:
    self.handle_multiple_of_ten()

def f(x=None):
    x = x or []
```

1. 注意, '0'(字符串, 不是整数)作为布尔值时等于 `True`.
1. 注意, 把 Numpy 数组转换为布尔值时可能抛出异常. 因此建议用 `.size` 属性检查 `np.array` 是否为空 (例如 `if not users.size`).

### 词法作用域(Lexical Scoping, 又名静态作用域)

> **提示：**
> 可以使用.

定义:
嵌套的Python函数可以引用外层函数中定义的变量, 但是不能对这些变量赋值. 变量的绑定分析基于词法作用域, 也就是基于静态的程序文本. 任何在代码块内给标识符赋值的操作, 都会让Python将该标识符的所有引用变成局部变量, 即使读取语句写在赋值语句之前. 如果有全局声明, 该标识符会被视为全局变量.

一个使用这个特性的例子:

```python
def get_adder(summand1: float) -> Callable[[float], float]:
    """返回一个函数，该函数会给一个数字加上指定的值."""
    def adder(summand2: float) -> float:
        return summand1 + summand2

    return adder
```

(译者注: 这个函数的用法大概是: `fn = get_adder(1.2); sum = fn(3.4)`, 结果是 `sum == 4.6`.)

优点:
通常会产生更清晰、更优雅的代码. 尤其是让熟练使用Lisp和Scheme(还有Haskell, ML等)的程序员感到舒适.

缺点:
可能引发让人困惑的bug, 例如下面这个依据 [PEP-0227 ](https://www.python.org/dev/peps/pep-0227/) 改编的例子:

```python
i = 4
def foo(x: Iterable[int]):
    def bar():
        print(i, end='')
    # ...
    # 很多其他代码
    # ...
    for i in x:  # 啊哈, i 是 Foo 的局部变量, 所以 bar 得到的是这个变量
        print(i, end='')
    bar()
```

因此 `foo([1, 2, 3])` 会输出 `1 2 3 3` , 而非 `1 2 3 4` .

(译者注: x是一个列表, for循环其实是将x中的值依次赋给i.这样对i的赋值就隐式的发生了, 整个foo函数体中的i都会被当做局部变量, 包括bar()中的那个. 这一点与C++之类的语言还是有很大差别的.)

结论:
可以使用.

### 函数与方法装饰器

> **提示：**
> 仅在有显著优势时, 审慎地使用装饰器. 避免使用 `staticmethod`. 减少使用 `classmethod`.

定义:
[装饰器(也就是@标记)作用在函数和方法上 ](https://docs.python.org/release/2.4.3/whatsnew/node6.html). 常见的装饰器是 `@property`, 用于把方法转化为动态求值的属性. 不过, 也可以用装饰器语法自行定义装饰器. 具体地说, 若有一个函数 `my_decorator` , 下面两段代码是等效的:

```python
class C(object):
   @my_decorator
   def method(self):
       # 函数体 ...
```

```python
class C(object):
    def method(self):
        # 函数体 ...
    method = my_decorator(method)
```

优点:
优雅地实现函数的变换; 这种变换可用于减少重复的代码, 或帮助检查不变式 (invariant).

缺点:
装饰器可以在函数的参数和返回值上执行任何操作, 这可能产生意外且隐蔽的效果. 而且, 装饰是在定义对象时执行. 模块级对象(类、模块级函数)的装饰器在导入模块时执行. 当装饰器代码出错时, 很难恢复正常控制流.

结论:
仅在有显著优势时, 审慎地使用装饰器. 装饰器的导入和命名规则与函数相同. 装饰器的pydoc注释应清楚地说明该函数是装饰器. 请为装饰器编写单元测试.

避免装饰器自身对外界的依赖(即不要依赖于文件, 套接字, 数据库连接等), 因为执行装饰器时(即导入模块时. `pydoc` 和其他工具也会导入你的模块) 可能无法连接到这些环境. 只要装饰器的调用参数正确, 装饰器应该 (尽最大努力) 保证运行成功.

装饰器是一种特殊形式的"顶级代码". 参见关于《Python风格规范》中“主程序”的章节.

不得使用 `staticmethod`, 除非为了兼容老代码库的 API 不得已而为之. 应该把静态方法改写为模块级函数.

仅在以下情况可以使用 `classmethod`: 实现具名构造函数(named constructor); 在类方法中修改必要的全局状态 (例如进程内共享的缓存等)。

### 线程

> **提示：**
> 不要依赖内置类型的原子性.

虽然Python的内置类型表面上有原子性, 但是在特定情形下可能打破原子性(例如用Python实现 `__hash__` 或 `__eq__` 的情况下). 因此它们的原子性不可靠. 你也不能臆测赋值是原子性的(因为赋值的原子性依赖于字典的原子性).

选择线程间的数据传递方式时, 应优先考虑 `queue` 模块的 `Queue` 数据类型. 如果不适用, 则使用 `threading` 模块及其提供的锁原语(locking primitives). 如果可行, 应该用条件变量和 `threading.Condition` 替代低级的锁.

### 威力过大的功能

> **提示：**
> 避开这些功能.

定义:
Python是一种异常灵活的语言, 有大量花哨的功能, 诸如自定义元类(metaclasses), 读取字节码(bytecode), 及时编译(on-the-fly compilation), 动态继承, 对象基类重设(object reparenting), 导入(import)技巧, 反射(例如 `getattr()`), 系统内部状态的修改, `__del__` 实现的自定义清理等等.

优点:
强大的语言功能让代码紧凑.

缺点:
这些很"酷"的功能十分诱人, 但多数情况下没必要使用. 包含奇技淫巧的代码难以阅读、理解和调试. 一开始可能还好(对原作者而言), 但以后回顾代码时, 这种代码通常比那些长而直白的代码更加深奥.

结论:
避开这些功能.

可以使用那些在内部利用了这些功能的标准模块和类, 比如 `abc.ABCMeta`, `dataclasses` 和 `enum`.

### 现代python: from __future__ imports

> **提示：**
> 可以通过导入 `__future__` 包, 在较老的运行时上启用新语法, 并且只在特定文件上生效.

定义:
通过使用 `from __future__ import` 并启用现代的语法, 可以提前使用未来的 Python 特性.

优点:
实践表明, 该功能可以让版本升级过程更稳定, 因为可以逐步修改各个文件, 并用这样的兼容性声明来防止退化 (regression). 现代的代码便于维护, 因为不容易积累那些阻碍运行时升级的技术债.

缺点:
此类代码无法在过老的运行时上运行, 过老的版本可能没有实现所需的 `future` 功能. 这个问题在那些需要支持大量不同环境的项目中尤为明显.

结论:
**from __future__ imports**

鼓励使用 `from __future__ import` 语句. 这样, 你的源代码从今天起就能使用更现代的 Python 语法. 当你不再需要支持老版本时, 请自行删除这些导入语句.

如果你的代码要支持 3.5 版本, 而不是常规的 `>=3.7`, 请导入:

```python
from __future__ import generator_stop
```

详情参见 [Python future 语句 ](https://docs.python.org/3/library/__future__.html) 的文档.

除非你确定代码的运行环境已经足够现代, 否则不要删除 future 语句. 即使你用不到 future 语句, 也要保留它们, 以免其他编辑者不小心对旧的特性产生依赖.

在你认为恰当的时候, 可以使用其他来自 `from __future__` 的语句.

### 代码类型注释

> **提示：**
> 你可以根据 [PEP-484 ](https://www.python.org/dev/peps/pep-0484/) 来对 python3 代码进行注释,并使用诸如 [pytype ](https://github.com/google/pytype) 之类的类型检查工具来检查代码.
>
> 类型注释既可以写在源码里,也可以写在 [pyi ](https://www.python.org/dev/peps/pep-0484/#stub-files) 中. 推荐尽量写在源码里. 对于第三方代码和扩展包, 请使用 pyi 文件.

定义:
用在函数参数和返回值上:

```python
def func(a: int) -> List[int]:
```

也可以使用 [PEP-526 ](https://www.python.org/dev/peps/pep-0526/) 中的语法来声明变量类型:

```python
a: SomeType = some_func()
```

优点:
可以提高代码可读性和可维护性. 类型检查器可以把运行时错误变成编译错误, 并阻止你使用威力过大的功能.

缺点:
必须时常更新类型声明. 正确的代码也可能有误报. 无法使用威力大的功能.

结论:
 强烈推荐你在更新代码时启用 python 类型分析. 在添加或修改公开API时, 请添加类型注释, 并在构建系统(build system)中启用 pytype. 由于python静态分析是新功能, 因此一些意外的副作用(例如类型推导错误)可能会阻碍你的项目采纳这一功能. 在这种情况下, 建议作者在 BUILD 文件或者代码中添加一个 TODO 注释或者链接, 描述那些阻碍采用类型注释的问题.

 (译者注: 代码类型注释在帮助IDE或是vim等进行补全倒是很有效)

## Python风格规范

### 分号

> **提示：**
> 不要在行尾加分号, 也不要用分号将两条语句合并到一行.

### 行宽

> **提示：**
> 最大行宽是 80 个字符.

例外:

1. 长的导入 (import) 语句.
1. 注释里的 URL、路径名以及长的标志 (flag).
1. 不便于换行、不包含空格、模块级的长字符串常量, 比如 URL 或路径名.
1. Pylint 禁用注释. (例如: `# pylint: disable=invalid-name`)

不要用反斜杠表示 [显式续行 (explicit line continuation) ](https://docs.python.org/3/reference/lexical_analysis.html#explicit-line-joining).

应该利用 Python 的 [圆括号, 中括号和花括号的隐式续行 (implicit line joining) ](https://docs.python.org/2/reference/lexical_analysis.html#implicit-line-joining) . 如有需要, 你可以在表达式外围添加一对括号.

正确:

```python
foo_bar(self, width, height, color='黑', design=None, x='foo',
        emphasis=None, highlight=0)

if (width == 0 and height == 0 and
    color == '红' and emphasis == '加粗'):

(bridge_questions.clarification_on
 .average_airspeed_of.unladen_swallow) = '美国的还是欧洲的?'

with (
    very_long_first_expression_function() as spam,
    very_long_second_expression_function() as beans,
    third_thing() as eggs,
):
    place_order(eggs, beans, spam, beans)
```

错误:

```python
if width == 0 and height == 0 and \
    color == '红' and emphasis == '加粗':

bridge_questions.clarification_on \
    .average_airspeed_of.unladen_swallow = '美国的还是欧洲的?'

with very_long_first_expression_function() as spam, \
        very_long_second_expression_function() as beans, \
        third_thing() as eggs:
    place_order(eggs, beans, spam, beans)
```

如果字符串的字面量 (literal) 超过一行, 应该用圆括号实现隐式续行:

```python
x = ('这是一个很长很长很长很长很长很长'
     '很长很长很长很长很长的字符串')
```

最好在最外层的语法结构上分行. 如果你需要多次换行, 应该在同一层语法结构上换行.

正确:

```python
bridgekeeper.answer(
     name="亚瑟", quest=questlib.find(owner="亚瑟", perilous=True))

 answer = (a_long_line().of_chained_methods()
           .that_eventually_provides().an_answer())

 if (
     config is None
     or 'editor.language' not in config
     or config['editor.language'].use_spaces is False
 ):
   use_tabs()
```

错误:

```python
bridgekeeper.answer(name="亚瑟", quest=questlib.find(
    owner="亚瑟", perilous=True))

answer = a_long_line().of_chained_methods().that_eventually_provides(
    ).an_answer()

if (config is None or 'editor.language' not in config or config[
    'editor.language'].use_spaces is False):
  use_tabs()
```

必要时, 注释中的长 URL 可以独立成行.

正确:

```python
# 详情参见
# https://www.example.com/us/developer/documentation/api/content/v2.0/csv_file_name_extension_full_specification.html
```

错误:

```python
# 详情参见
# https://www.example.com/us/developer/documentation/api/content/\
# v2.0/csv_file_name_extension_full_specification.html
```

注意上面各个例子中的缩进; 详情参见 缩进  章节的解释.

如果一行超过 80 个字符, 且 [Black ](https://github.com/psf/black) 或 [Pyink ](https://github.com/google/pyink) 自动格式化工具无法继续缩减行宽, 则允许该行超过 80 个字符. 我们也鼓励作者根据上面的规则手动拆分.

### 括号

> **提示：**
> 使用括号时宁缺毋滥.

可以把元组 (tuple) 括起来, 但不强制. 不要在返回语句或条件语句中使用括号, 除非用于隐式续行或表示元组.

正确:

```python
if foo:
    bar()
while x:
    x = bar()
if x and y:
    bar()
if not x:
    bar()
# 对于包含单个元素的元组, 括号比逗号更直观.
onesie = (foo,)
return foo
return spam, beans
return (spam, beans)
for (x, y) in dict.items(): ...
```

错误:

```python
if (x):
    bar()
if not(x):
    bar()
return (foo)
```

### 缩进

> **提示：**
> 用4个空格作为缩进.

不要使用制表符. 使用隐式续行时, 应该把括起来的元素垂直对齐(参见 行宽  章节的示例), 或者添加4个空格的悬挂缩进. 右括号 (圆括号, 方括号或花括号) 可以置于表达式结尾或者另起一行. 另起一行时右括号应该和左括号所在的那一行缩进相同.

正确:

```python
# 与左括号对齐.
foo = long_function_name(var_one, var_two,
                         var_three, var_four)
meal = (spam,
        beans)

# 与字典的左括号对齐.
foo = {
    'long_dictionary_key': value1 +
                           value2,
    ...
}

# 4个空格的悬挂缩进; 首行没有元素
foo = long_function_name(
    var_one, var_two, var_three,
    var_four)
meal = (
    spam,
    beans)

# 4个空格的悬挂缩进; 首行没有元素
# 右括号另起一行.
foo = long_function_name(
    var_one, var_two, var_three,
    var_four
)
meal = (
    spam,
    beans,
)

# 字典中的4空格悬挂缩进.
foo = {
    'long_dictionary_key':
        long_dictionary_value,
    ...
}
```

错误:

```python
# 首行不能有元素.
foo = long_function_name(var_one, var_two,
    var_three, var_four)

# 禁止2个空格的悬挂缩进.
foo = long_function_name(
  var_one, var_two, var_three,
  var_four)

# 字典没有悬挂缩进.
foo = {
    'long_dictionary_key':
    long_dictionary_value,
    ...
}
```

### 序列的尾部要添加逗号吗?

> **提示：**
> 仅当 `]`, `)`, `}` 和最后一个元素不在同一行时, 推荐在序列尾部添加逗号. 我们的 Python 自动格式化工具会把尾部的逗号视为一种格式提示.

### Shebang行

> **提示：**
> 大部分 `.py` 文件不必以 `#!` 开始. 可以根据 [PEP-394 ](https://www.python.org/dev/peps/pep-0394/) , 在程序的主文件开头添加 `#!/usr/bin/env python3` (以支持 virtualenv) 或者 `#!/usr/bin/python3`.

(译者注: 在计算机科学中, [Shebang ](https://en.wikipedia.org/wiki/Shebang_(Unix)) (也称为Hashbang)是一个由井号和叹号构成的字符串行(#!), 其出现在文本文件的第一行的前两个字符. 在文件中存在Shebang的情况下, 类Unix操作系统的程序载入器会分析Shebang后的内容, 将这些内容作为解释器指令, 并调用该指令, 并将载有Shebang的文件路径作为该解释器的参数. 例如, 以指令#!/bin/sh开头的文件在执行时会实际调用/bin/sh程序.)

内核会通过这行内容找到Python解释器, 但是Python解释器在导入模块时会忽略这行内容. 这行内容仅对需要直接运行的文件有效.

### 注释和文档字符串 (docstring)

> **提示：**
> 模块、函数、方法的文档字符串和内部注释一定要采用正确的风格.

**文档字符串**

Python 的文档字符串用于注释代码. 文档字符串是包、模块、类或函数里作为第一个语句的字符串. 可以用对象的 `__doc__` 成员自动提取这些字符串, 并为 `pydoc` 所用. (可以试试在你的模块上运行 `pydoc` 并观察结果). 文档字符串一定要用三重双引号 `"""` 的格式 (依据 [PEP-257 ](https://www.python.org/dev/peps/pep-0257/) ). 文档字符串应该是一行概述 (整行不超过 80 个字符), 以句号、问号或感叹号结尾. 如果要写更多注释 (推荐), 那么概述后面必须紧接着一个空行, 然后是剩下的内容, 缩进与文档字符串的第一行第一个引号对齐. 下面是更多有关文档字符串的格式规范.

**模块**

每个文件应该包含一个许可协议模版. 应根据项目使用的许可协议 (例如, Apache 2.0, BSD, LGPL, GPL) 选择合适的模版.

文件的开头应该是文档字符串, 其中应该描述该模块内容和用法.

```python
"""模块或程序的一行概述, 以句号结尾.

留一个空行. 接下来应该写模块或程序的总体描述. 也可以选择简要描述导出的类和函数,
和/或描述使用示例.

经典的使用示例:

foo = ClassFoo()
bar = foo.FunctionBar()
"""
```

**测试模块**

测试文件不必包含模块级文档字符串. 只有在文档字符串可以提供额外信息时才需要写入文件.

例如, 你可以描述运行测试时所需的特殊要求, 解释不常见的初始化模式, 描述外部环境的依赖等等.

```python
"""这个blaze测试会使用样板文件（golden files）.

若要更新这些文件, 你可以在 `google3` 文件夹中运行
`blaze run //foo/bar:foo_test -- --update_golden_files`
"""
```

不要使用不能提供额外信息的文档字符串.

```python
"""foo.bar 的测试."""
```

**函数和方法**

本节中的函数是指函数、方法、生成器 (generator) 和特性 (property).

满足下列任意特征的任何函数都必须有文档字符串:

1. 公开 API 的一部分
1. 长度过长
1. 逻辑不能一目了然

文档字符串应该提供充分的信息, 让调用者无需阅读函数的代码就能调用函数. 文档字符串应该描述函数的调用语法和语义信息, 而不应该描述具体的实现细节, 除非这些细节会影响函数的用法. 比如, 如果函数的副作用是会修改某个传入的对象, 那就需要在文档字符串中说明. 对于微妙、重要但是与调用者无关的实现细节, 相较于在文档字符串里说明, 还是在代码中间加注释更好.

文档字符串可以是陈述句 (`"""Fetches rows from a Bigtable."""`) 或者祈使句 (`"""Fetch rows from a Bigtable."""`), 不过一个文件内的风格应当一致. 对于 `@property` 修饰的数据描述符 (data descriptor), 文档字符串应采用和属性 (attribute) 或 函数参数  一样的风格 (`"""Bigtable 路径."""` 而非 `"""返回 Bigtable 路径."""`).

对于覆写 (override) 基类 (base class) 方法的子类方法, 可以用简单的文档字符串引导读者阅读基类方法的文档字符串, 比如 `"""参见基类.""""`. 这样是为了避免到处复制基类方法中已有的文档字符串. 然而, 如果覆写的子类方法与基类方法截然不同, 或者有更多细节需要记录 (例如有额外的的副作用), 那么子类方法的文档字符串中至少要描述这些区别.

函数的部分特征应该在以下列出特殊小节中记录. 每小节有一行标题, 标题以冒号结尾. 除标题行外, 小节的其他部分应有2个或4个空格 (同一文件内应保持一致) 的悬挂缩进. 如果函数名和函数签名 (signature) 可以见名知意, 以至于一行文档字符串就能恰当地描述该函数, 那么可以省略这些小节.

Args: (参数:)
    列出所有参数名. 参数名后面是一个冒号, 然后是一个空格或者换行符, 最后是描述. 如果描述过长以至于一行超出了 80 字符, 则描述部分应该比参数名所在的行多2个或者4个空格 (文件内应当一致) 的悬挂缩进. 如果代码没有类型注解, 则描述中应该说明所需的类型. 如果一个函数有形如 `*foo` (可变长参数列表) 或者 `**bar` (任意关键字参数) 的参数, 那么列举参数名时应该写成 `*foo` 和 `**bar` 的这样的格式.

Returns: ("返回:")
    生成器应该用 "Yields:" ("生成:" )

    描述返回值的类型和意义. 如果函数仅仅返回 `None`, 这一小节可以省略. 如果文档字符串以 Returns (返回) 或者 Yields (生成) 开头 (例如 `"""返回 Bigtable 的行, 类型是字符串构成的元组."""`) 且这句话已经足以描述返回值, 也可以省略这一小节. 不要模仿 Numpy 风格的文档 ([例子 ](https://numpy.org/doc/stable/reference/generated/numpy.linalg.qr.html)). 他们在文档中记录作为返回值的元组时, 写得就像返回值是多个值且每个值都有名字 (没有提到返回的是元组). 应该这样描述此类情况: "返回: 一个元组 (mat_a, mat_b), 其中 mat_a 是..., 且 ...". 文档字符串中使用的辅助名称不需要和函数体的内部变量名一致 (因为这些名称不是 API 的一部分).

Raises: (抛出:)
    列出与接口相关的所有异常和异常描述. 用类似 Args (参数) 小节的格式，写成异常名+冒号+空格/换行, 并添加悬挂缩进. 不要在文档中记录违反 API 的使用条件时会抛出的异常 (因为这会让违背 API 时出现的效果成为 API 的一部分, 这是矛盾的).

```python
def fetch_smalltable_rows(
    table_handle: smalltable.Table,
    keys: Sequence[bytes | str],
    require_all_keys: bool = False,
) -> Mapping[bytes, tuple[str, ...]]:
    """从 Smalltable 获取数据行.

    从 table_handle 代表的 Table 实例中检索指定键值对应的行. 如果键值是字符串,
    字符串将用 UTF-8 编码.

    参数:
        table_handle: 处于打开状态的 smalltable.Table 实例.
        keys: 一个字符串序列, 代表要获取的行的键值. 字符串将用 UTF-8 编码.
        require_all_keys: 如果为 True, 只返回那些所有键值都有对应数据的
            行.

    返回:
        一个字典, 把键值映射到行数据上. 行数据是字符串构成的元组. 例如:

        {b'Serak': ('Rigel VII', 'Preparer'),
         b'Zim': ('Irk', 'Invader'),
         b'Lrrr': ('Omicron Persei 8', 'Emperor')}

        返回的键值一定是字节串. 如果字典中没有 keys 参数中的某个键值, 说明
        表格中没有找到这一行 (且 require_all_keys 一定是 false).

    抛出:
        IOError: 访问 smalltable 时出现错误.
    """
```

以下这种在 Args (参数) 小节中换行的写法也是可以的:

```python
def fetch_smalltable_rows(
    table_handle: smalltable.Table,
    keys: Sequence[bytes | str],
    require_all_keys: bool = False,
) -> Mapping[bytes, tuple[str, ...]]:
    """从 Smalltable 获取数据行.

    从 table_handle 代表的 Table 实例中检索指定键值对应的行. 如果键值是字符串,
    字符串将用 UTF-8 编码.

    参数:
        table_handle:
          处于打开状态的 smalltable.Table 实例.
        keys:
          一个字符串序列, 代表要获取的行的键值. 字符串将用 UTF-8 编码.
        require_all_keys:
          如果为 True, 只返回那些所有键值都有对应数据的行.

    返回:
        一个字典, 把键值映射到行数据上. 行数据是字符串构成的元组. 例如:

        {b'Serak': ('Rigel VII', 'Preparer'),
         b'Zim': ('Irk', 'Invader'),
         b'Lrrr': ('Omicron Persei 8', 'Emperor')}

        返回的键值一定是字节串. 如果字典中没有 keys 参数中的某个键值, 说明
        表格中没有找到这一行 (且 require_all_keys 一定是 false).

    抛出:
        IOError: 访问 smalltable 时出现错误.
    """
```

**类 (class)**

类的定义下方应该有一个描述该类的文档字符串. 如果你的类包含公有属性 (attributes), 应该在 `Attributes` (属性) 小节中记录这些属性, 格式与函数的 `Args` (参数) 小节类似.

```python
class SampleClass(object):
    """这里是类的概述.

    这里是更多信息....
    这里是更多信息....

    属性:
        likes_spam: 布尔值, 表示我们是否喜欢午餐肉.
        eggs: 用整数记录的下蛋的数量.
    """

    def __init__(self, likes_spam = False):
        """用某某某初始化 SampleClass."""
        self.likes_spam = likes_spam
        self.eggs = 0

    def public_method(self):
        """执行某某操作."""
```

类的文档字符串开头应该是一行概述, 描述类的实例所代表的事物. 这意味着 `Exception` 的子类 (subclass) 应该描述这个异常代表什么, 而不是描述抛出异常时的环境. 类的文档字符串不应该有无意义的重复, 例如说这个类是一种类.

正确:

```python
class CheeseShopAddress:
"""奶酪店的地址.

...
"""

class OutOfCheeseError(Exception):
"""没有可用的奶酪."""
```

错误:

```python
class CheeseShopAddress:
"""一个描述奶酪店地址的类.

...
"""

class OutOfCheeseError(Exception):
"""在没有可用的奶酪时抛出."""
```

**块注释和行注释**

最后一种需要写注释的地方是代码中复杂的部分. 如果你可能在以后 [代码评审 (code review) ](https://en.wikipedia.org/wiki/Code_review) 时要解释某段代码, 那么现在就应该给这段代码加上注释. 应该在复杂的操作开始前写上若干行注释. 对于不是一目了然的代码, 应该在行尾添加注释.

```python
# 我们用加权的字典搜索, 寻找 i 在数组中的位置. 我们基于数组中的最大值和数组
# 长度, 推断一个位置, 然后用二分搜索获得最终准确的结果.

if i & (i-1) == 0:  # 如果 i 是 0 或者 2 的整数次幂, 则为真.
```

为了提高可读性, 注释的井号和代码之间应有至少2个空格, 井号和注释之间应该至少有一个空格.

除此之外, 绝不要仅仅描述代码. 应该假设读代码的人比你更懂Python, 只是不知道你的代码要做什么.

```python
# 不好的注释: 现在遍历数组 b, 确保每次 i 出现时, 下一个元素是 i+1
```

### 标点符号、拼写和语法

> **提示：**
> 注意标点符号、拼写和语法. 文笔好的注释比差的注释更容易理解.

注释应该和记叙文一样可读, 使用恰当的大小写和标点. 一般而言, 完整的句子比残缺句更可读. 较短的注释 (比如行尾注释) 可以更随意, 但是你要保持风格一致.

尽管你可能会因为代码审稿人指出你误把冒号写作逗号而灰心, 但是保持源代码清晰可读也是非常重要的. 正确的标点、拼写和语法有助于实现这一目标.

### 字符串

> **提示：**
> 应该用 [f-string ](https://docs.python.org/zh-cn/3/reference/lexical_analysis.html#f-strings)、 `%` 运算符或 `format` 方法来格式化字符串. 即使所有参数都是字符串, 也如此. 你可以自行评判合适的选项. 可以用 `+` 实现单次拼接, 但是不要用 `+` 实现格式化.

正确:

```python
x = f'名称: {name}; 分数: {n}'
x = '%s, %s!' % (imperative, expletive)
x = '{}, {}'.format(first, second)
x = '名称: %s; 分数: %d' % (name, n)
x = '名称: %(name)s; 分数: %(score)d' % {'name':name, 'score':n}
x = '名称: {}; 分数: {}'.format(name, n)
x = a + b
```

错误:

```python
x = first + ', ' + second
x = '名称: ' + name + '; 分数: ' + str(n)
```

不要在循环中用 `+` 和 `+=` 操作符来堆积字符串. 这有时会产生平方而不是线性的时间复杂度. 有时 CPython 会优化这种情况, 但这是一种实现细节. 我们无法轻易预测这种优化是否生效, 而且未来情况可能出现变化. 作为替代方案, 你可以将每个子串加入列表, 然后在循环结束后用 `''.join` 拼接列表. 也可以将每个子串写入一个 `io.StringIO` 缓冲区中. 这些技巧保证始终有线性的平摊 (amortized) 时间复杂度.

正确:

```python
items = ['<table>']
for last_name, first_name in employee_list:
    items.append('<tr><td>%s, %s</td></tr>' % (last_name, first_name))
items.append('</table>')
employee_table = ''.join(items)
```

错误:

```python
employee_table = '<table>'
for last_name, first_name in employee_list:
    employee_table += '<tr><td>%s, %s</td></tr>' % (last_name, first_name)
employee_table += '</table>'
```

应该保持同一文件中字符串引号的一致性. 选择 `'` 或者 `"` 以后不要改变主意. 如果需要避免用反斜杠来转义引号, 则可以使用另一种引号.

正确:

```python
Python('为什么你要捂眼睛?')
Gollum("I'm scared of lint errors. (我害怕格式错误.)")
Narrator('"很好!" 一个开心的 Python 审稿人心想.')
```

(译者注: 注意 "I'm" 中间有一个单引号，所以这一行的外层引号可以用不同的引号.)

错误:

```python
Python("为什么你要捂眼睛?")
Gollum('格式检查器. 它在闪耀. 它要亮瞎我们.')
Gollum("伟大的格式检查器永在. 它在看. 它在看.")
```

多行字符串推荐使用 `"""` 而非 `'''`. 当且仅当项目中用 `'` 给常规字符串打引号时, 才能在文档字符串以外的多行字符串上使用 `'''`. 无论如何, 文档字符串必须使用 `"""`.

多行字符串不会跟进代码其他部分的缩进. 如果需要避免字符串中的额外空格, 可以用多个单行字符串拼接, 或者用 [textwrap.dedent() ](https://docs.python.org/zh-cn/3/library/textwrap.html#textwrap.dedent) 删除每行开头的空格.

错误:

```python
    long_string = """这样很难看.
不要这样做.
"""
```

正确:

```python
long_string = """如果你可以接受多余的空格,
    就可以这样."""

long_string = ("如果你不能接受多余的空格,\n" +
               "可以这样.")

long_string = ("如果你不能接受多余的空格,\n"
               "也可以这样.")
```

```python
import textwrap

long_string = textwrap.dedent("""\
  这样也行, 因为 textwrap.dedent()
  会删除每一行开头共有的空格.""")
```

注意, 这里的反斜杠没有违反 显式续行的禁令 . 此时, 反斜杠用于在字符串字面量 (literal) 中 [对换行符转义 ](https://docs.python.org/zh-cn/3/reference/lexical_analysis.html#string-and-bytes-literals).

**日志**

对于那些第一个参数是格式字符串 (包含 `%` 占位符) 的日志函数: 一定要用字符串字面量 (而非 f-string!) 作为第一个参数, 并用占位符的参数作为其他参数. 有些日志的实现会收集未展开的格式字符串, 作为可搜索的项目. 这样也可以免于渲染那些被设置为不用输出的消息.

正确；

```python
import tensorflow as tf
logger = tf.get_logger()
logger.info('TensorFlow 的版本是: %s', tf.__version__)
```

```python
import os
from absl import logging

logging.info('当前的 $PAGER 是: %s', os.getenv('PAGER', default=''))

homedir = os.getenv('HOME')
if homedir is None or not os.access(homedir, os.W_OK):
    logging.error('无法写入主目录, $HOME=%r', homedir)
```

错误:

```python
import os
from absl import logging

logging.info('当前的 $PAGER 是:')
logging.info(os.getenv('PAGER', default=''))

homedir = os.getenv('HOME')
if homedir is None or not os.access(homedir, os.W_OK):
    logging.error(f'无法写入主目录, $HOME={homedir!r}')
```

**错误信息**

错误信息 (例如: 诸如 `ValueError` 等异常的信息字符串和展示给用户的信息) 应该遵守以下三条规范:

1. 信息需要精确地匹配真正的错误条件.
1. 插入的片段一定要能清晰地分辨出来.
1. 要便于简单的自动化处理 (例如正则搜索, 也就是 grepping).

正确:

```python
if not 0 <= p <= 1:
    raise ValueError(f'这不是概率值: {p!r}')

try:
    os.rmdir(workdir)
except OSError as error:
    logging.warning('无法删除这个文件夹 (原因: %r): %r',
                    error, workdir)
```

错误:

```python
if p < 0 or p > 1:  # 问题: 遇到 float('nan') 时也为假!
    raise ValueError(f'这不是概率值: {p!r}')

try:
    os.rmdir(workdir)
except OSError:
    # 问题: 信息中存在错误的揣测，
    # 删除操作可能因为其他原因而失败, 此时会误导调试人员.
    logging.warning('文件夹已被删除: %s', workdir)

try:
    os.rmdir(workdir)
except OSError:
    # 问题: 这个信息难以搜索, 而且某些 `workdir` 的值会让人困惑.
    # 假如有人调用这段代码时让 workdir = '已删除'. 这个警告会变成:
    # "无法删除已删除文件夹."
    logging.warning('无法删除%s文件夹.', workdir)
```

### 文件、套接字 (socket) 和类似的有状态资源

> **提示：**
> 使用完文件和套接字以后, 显式地关闭它们. 自然地, 这条规则也应该扩展到其他在内部使用套接字的可关闭资源 (比如数据库连接) 和其他需要用类似方法关停的资源. 其他例子还有 [mmap ](https://docs.python.org/zh-cn/3/library/mmap.html) 映射、 [h5py 的文件对象 ](https://docs.h5py.org/en/stable/high/file.html) 和 [matplotlib.pyplot 的图像窗口 ](https://matplotlib.org/2.1.0/api/_as_gen/matplotlib.pyplot.close.html) .

如果保持不必要的文件、套接字或其他有状态对象开启, 会产生很多缺点:

1. 它们可能消耗有限的系统资源, 例如文件描述符. 如果代码需要使用大量类似的资源而没有及时返还给系统, 就有可能出现原本可以避免的资源枯竭情况.
1. 保持文件的开启状态会阻碍其他操作, 例如移动、删除文件, 卸载 (unmont) 文件系统等等.
1. 如果程序的多个部分共享文件和套接字, 即使逻辑上文件已经关闭了, 仍然有可能出现意外的读写操作. 如果这些资源真正关闭了, 读写操作会抛出异常, 让问题早日浮出水面.

此外, 即使文件和套接字 (以及其他行为类似的资源) 会在析构 (destruct) 时自动关闭, 把对象的生命周期和资源状态绑定的行为依然不妥:

1. 无法保证运行时 (runtime) 调用 `__del__` 方法的真正时机. 不同的 Python 实现采用了不同的内存管理技巧 (比如延迟垃圾处理机制, delayed garbage collection), 可能会随意、无限期地延长对象的生命周期.
1. 意想不到的文件引用 (例如全局对象和异常的堆栈跟踪, exception tracebacks) 可能让文件的存续时间比想象的更长.

依赖于终结器 (finalizer) 实现自动清理的方法有显著的副作用. 这在几十年的时间里、在多种语言中 (参见 [这篇 ](https://wiki.sei.cmu.edu/confluence/display/java/MET12-J.+Do+not+use+finalizers) Java 的文章) 多次引发严重问题.

推荐使用 ["with"语句 ](https://docs.python.org/zh-cn/3/reference/compound_stmts.html#the-with-statement) 管理文件和类似的资源:

```python
with open("hello.txt") as hello_file:
    for line in hello_file:
        print line
```

对于不支持 `with` 语句且类似文件的对象, 应该使用 `contextlib.closing()`:

```python
import contextlib

with contextlib.closing(urllib.urlopen("https://www.python.org/")) as front_page:
    for line in front_page:
        print line
```

少数情况下无法使用基于上下文 (context) 的资源管理, 此时文档应该清楚地解释代码会如何管理资源的生命周期.

### TODO (待办) 注释

> **提示：**
> 在临时、短期和不够完美的代码上添加 TODO (待办) 注释.

待办注释以 `TODO` (待办) 这个全部大写的词开头, 紧跟着是用括号括起来的上下文标识符 (最好是 bug 链接, 有时是你的用户名). 最好是诸如 `TODO(https://crbug.com/<bug编号>):` 这样的 bug 链接, 因为 bug 有历史追踪和评论, 而程序员可能发生变动并忘记上下文. TODO 后面应该解释待办的事情.

统一 TODO 的格式是为了方便搜索并查看详情. TODO 不代表注释中提到的人要做出修复问题的保证. 所以, 当你创建带有用户名的 TODO 时, 大部分情况下应该用你自己的用户名.

```python
# TODO(crbug.com/192795): 研究 cpufreq 的优化.
# TODO(你的用户名): 提交一个议题 (issue), 用 '*' 代表重复.
```

如果你的 TODO 形式类似于"将来做某事", 请确保其中包含特别具体的日期 ("2009年11月前解决") 或者特别具体的事件 ("当所有客户端都能处理 XML 响应时, 删除这些代码"), 以便于未来的代码维护者理解.

### 导入 (import) 语句的格式

> **提示：**
> 导入语句应该各自独占一行. typing 和 collections.abc 的导入除外 . 例如:

正确:

```python
from collections.abc import Mapping, Sequence
import os
import sys
from typing import Any, NewType
```

错误:

```python
import os, sys
```

导入语句必须在文件顶部, 位于模块的注释和文档字符串之后、全局变量和全局常量之前. 导入语句应该按照如下顺序分组, 从通用到特殊:

1. 导入 Python 的 `__future__`. 例如:

```python
from __future__ import annotations
```

参见前文有关 `__future__` 语句的描述.

1. 导入 Python 的标准库. 例如:

```python
import sys
```

1. 导入 [第三方 ](https://pypi.org/) 模块和包. 例如:

```python
import tensorflow as tf
```

1. 导入代码仓库中的子包. 例如:

```python
from otherproject.ai import mind
```

1. **已废弃的规则**: 导入应用专属的、与该文件属于同一个子包的模块. 例如:

```python
from myproject.backend.hgwells import time_machine
```

你可能会在较老的谷歌风格 Python 代码中遇到这样的模式, 但现在不再执行这条规则. **我们建议新代码忽略这条规则.** 同等对待应用专属的子包和其他子包即可.

在每个分组内部, 应该按照模块完整包路径 (例如 `from path import ...` 中的 `path`) 的字典序排序, 忽略大小写. 可以选择在分组之间插入空行.

```python
import collections
import queue
import sys

from absl import app
from absl import flags
import bs4
import cryptography
import tensorflow as tf

from book.genres import scifi
from myproject.backend import huxley
from myproject.backend.hgwells import time_machine
from myproject.backend.state_machine import main_loop
from otherproject.ai import body
from otherproject.ai import mind
from otherproject.ai import soul

# 旧的代码可能会把这些导入语句放在下面这里:
#from myproject.backend.hgwells import time_machine
#from myproject.backend.state_machine import main_loop
```

### 语句

> **提示：**
> 通常每个语句应该独占一行.

不过, 如果判断语句的主体与判断条件可以挤进一行, 你可以将它们放在同一行. 特别注意这不适用于 `try` / `except`, 因为 `try` 和 `except` 不能放在同一行. 只有在 `if` 语句没有对应的 `else` 时才适用.

正确:

```python
if foo: bar(foo)
```

错误:

```python
if foo: bar(foo)
else:   baz(foo)

try:               bar(foo)
except ValueError: baz(foo)

try:
    bar(foo)
except ValueError: baz(foo)
```

### 访问器 (getter) 和设置器 (setter)

> **提示：**
> 在访问和设置变量值时, 如果访问器和设置器 (又名为访问子 accessor 和变异子 mutator) 可以产生有意义的作用或效果, 则可以使用.

特别来说, 如果在当下或者可以预见的未来, 读写某个变量的过程很复杂或者成本高昂, 则应该使用这种函数.

如果一对访问器和设置器仅仅用于读写一个内部属性 (attribute), 你应该直接用公有属性取代它们. 相较而言, 如果设置操作会让部分状态无效化或引发重建, 则需要使用设置器. 显式的函数调用表示可能出现特殊的操作. 如果只有简单的逻辑, 或者在重构代码后不再需要访问器和设置器, 你可以用属性 (property) 替代.

(译者注: 重视封装的面向对象程序员看到这个可能会很反感, 因为他们一直被教育: 所有成员变量都必须是私有的! 其实, 那真的是有点麻烦啊. 试着去接受Pythonic哲学吧)

访问器和设置器应该遵守命名规范, 例如 `get_foo()` 和 `set_foo()`.

如果之前的代码通过属性获取数据, 则不能把重新编写的访问器/设置器与这一属性绑定. 应该让任何用老办法访问变量的代码出现显眼的错误, 让使用者意识到代码复杂度有变化.

### 命名

> **提示：**
> 模块名: `module_name`; 包名: `package_name`; 类名: `ClassName`; 方法名: `method_name`; 异常名: `ExceptionName`; 函数名: `function_name`, `query_proper_noun_for_thing`, `send_acronym_via_https`; 全局常量名: `GLOBAL_CONSTANT_NAME` ; 全局变量名: `global_var_name`; 实例名: `instance_var_name`; 函数参数名: `function_parameter_name`; 局部变量名: `local_var_name`.

函数名、变量名和文件名应该是描述性的, 避免缩写. 特别要避免那些对于项目之外的人有歧义或不熟悉的缩写, 也不要通过省略单词中的字母来进行缩写.

必须用 `.py` 作为文件后缀名. 不要用连字符.

**需要避免的名称**

1. 只有单个字符的名称, 除了以下特别批准的情况:

    1. 计数器和迭代器 (例如, `i`, `j`, `k`, `v` 等等).
    1. 在 `try/except` 语句中代表异常的 `e`.
    1. 在 `with` 语句中代表文件句柄的 `f`.
    1. 私有的、没有约束 (constrain) 的类型变量 (type variable, 例如 `_T = TypeVar("_T")`, `_P = ParamSpec("_P")`).

1. 包含连字符(`-`) 的包名/模块名.
1. 首尾均为双下划线的名称, 例如 `__double_leading_and_trailing_underscore__` (此类名称是 Python 的保留名称).
1. 包含冒犯性词语的名称.
1. 在不必要的情况下包含变量类型的名称 (例如 `id_to_name_dict`).

**命名规范**

1. "内部(Internal)"一词表示仅在模块内可用, 或者在类内是受保护/私有的.
1. 在一定程度上, 在名称前加单下划线 (`_`) 可以保护模块变量和函数 (格式检查器会对受保护的成员访问操作发出警告).
1. 在实例的变量或方法名称前加双下划线 (`__`, 又名为 dunder) 可以有效地把变量或方法变成类的私有成员 (基于名称修饰 name mangling 机制). 我们不鼓励这种用法, 因为这会严重影响可读性和可测试性, 而且没有 **真正** 实现私有. 建议使用单下划线.
1. 应该把相关的类和顶级函数放在同一个模块里. 与Java不同, 不必限制一个模块只有一个类.
1. 类名应该使用首字母大写的形式 (如 CapWords), 但是模块名应该用小写加下划线的形式 (如 lower_with_under.py). 尽管有些旧的模块使用类似于 CapWords.py 这样的形式, 现在我们不再鼓励这种命名方式, 因为模块名和类名相同时会让人困惑 ("等等, 我刚刚写的是 `import StringIO` 还是 `from StringIO import StringIO`?").
1. 新的 **单元测试** 文件应该遵守 PEP 8, 用小写加下划线格式的方法名, 例如 `test_<被测试的方法名>_<状态>`. 有些老旧的模块有形如 `CapWords` 这样大写的方法名, 为了保持风格一致, 可以在 test 这个词和方法名之后, 用下划线分割名称中不同的逻辑成分. 比如一种可行的格式之一是 `test<被测试的方法>_<状态>`.

**文件名**

所有 Python 文件名都应该以 `.py` 为文件后缀且不能包含连字符 (`-`). 这样便于导入这些文件并编写单元测试. 如果想通过不含后缀的命令运行程序, 可以使用软链接文件 (symbolic link) 或者 `exec "$0.py" "$@"` 这样简单的 bash 脚本.

**根据Python之父Guido的建议所制定的规范**

   :widths: 30 30 40
   :header-rows: 1

   * - 类型
 - 公有
 - 内部
   * - 包
### - 小写下划线

   * - 模块
 - 小写下划线
 - 下划线+小写下划线
   * - 类
 - 大驼峰
 - 下划线+大驼峰
   * - 异常
### - 大驼峰

   * - 函数
 - 小写下划线
 - 下划线+小写下划线
   * - 全局常量/类常量
 - 大写下划线
 - 下划线+大写下划线
   * - 全局变量/类变量
 - 小写下划线
 - 下划线+小写下划线
   * - 实例变量
 - 小写下划线
 - 下划线+小写下划线 (受保护)
   * - 方法名
 - 小写下划线
 - 下划线+小写下划线 (受保护)
   * - 函数参数/方法参数
### - 小写下划线

   * - 局部变量
### - 小写下划线

   :widths: 30 35 35
   :header-rows: 1

   * - 类型
 - 公有
 - 内部
   * - 包
### - `lower_with_under`

   * - 模块
 - `lower_with_under`
 - `_lower_with_under`
   * - 类
 - `CapWords`
 - `_CapWords`
   * - 异常
### - `CapWords`

   * - 函数
 - `lower_with_under()`
 - `_lower_with_under()`
   * - 全局常量/类常量
 - `CAPS_WITH_UNDER`
 - `_CAPS_WITH_UNDER`
   * - 全局变量/类变量
 - `lower_with_under`
 - `_lower_with_under`
   * - 实例变量
 - `lower_with_under`
 - `_lower_with_under`
   * - 方法名
 - `lower_with_under()`
 - `_lower_with_under()`
   * - 函数参数/方法参数
### - `lower_with_under`

   * - 局部变量
### - `lower_with_under`

**数学符号**

对于涉及大量数学内容的代码, 如果相关论文或算法中有对应的符号, 则可以忽略以上命名规范并使用较短的变量名. 若要采用这种方法, 应该在注释或者文档字符串中注明你所使用的命名规范的来源. 如果原文无法访问, 则应该在文档中清楚地记录命名规范. 建议公开的 API 使用符合 PEP8 的、描述性的名称, 因为使用 API 的代码很可能缺少相关的上下文信息.

### 主程序

> **提示：**
> 使用 Python 时, 提供给 `pydoc` 和单元测试的模块必须是可导入的. 如果一个文件是可执行文件, 该文件的主要功能应该位于 `main()` 函数中. 你的代码必须在执行主程序前检查 `if __name__ == '__main__'` , 这样导入模块时不会执行主程序.

使用 [absl ](https://github.com/abseil/abseil-py) 时, 请调用 `app.run` :

```python
from absl import app
...

def main(argv):
    # 处理非标志 (non-flag) 参数
    ...

if __name__ == '__main__':
    app.run(main)
```

否则, 使用:

```python
def main():
    ...

if __name__ == '__main__':
    main()
```

导入模块时会执行该模块的所有顶级代码. 注意顶级代码中不能有 `pydoc` 不该执行的操作, 比如调用函数, 创建对象等.

### 函数长度

> **提示：**
> 函数应该小巧且专一.

我们承认有时长函数也是合理的, 所以不硬性限制函数长度. 若一个函数超过 40 行, 应该考虑在不破坏程序结构的前提下拆分这个函数.

即使一个长函数现在没有问题, 几个月后可能会有别人添加新的效果. 此时容易出现隐蔽的错误. 保持函数简练, 这样便于别人阅读并修改你的代码.

当你使用某些代码时, 可能发现一些冗长且复杂的函数. 要勇于修改现有的代码: 如果该函数难以使用或者存在难以调试的错误, 亦或是你想在不同场景下使用该函数的片段, 不妨考虑把函数拆分成更小、更容易管理的片段.

### 类型注解 (type annotation)

**通用规则**

1. 熟读 [PEP-484 ](https://www.python.org/dev/peps/pep-0484/) .
1. 仅在有额外类型信息时才需要注解方法中 `self` 或 `cls` 的类型. 例如:

```python
@classmethod
def create(cls: Type[_T]) -> _T:
    return cls()
```

1. 类似地, 不需要注解 `__init__` 的返回值 (只能返回 `None`).
1. 对于其他不需要限制变量类型或返回类型的情况, 应该使用 `Any`.
1. 无需注解模块中的所有函数.

    1. 至少需要注解你的公开 API.
    1. 你可以自行权衡, 一方面要保证代码的安全性和清晰性, 另一方面要兼顾灵活性.
    1. 应该注解那些容易出现类型错误的代码 (比如曾经出现过错误或疑难杂症).
    1. 应该注解晦涩难懂的代码.
    1. 应该注解那些类型已经确定的代码. 多数情况下，即使注解了成熟的代码中所有的函数，也不会丧失太多灵活性.

**换行**

尽量遵守前文所述的缩进规则.

添加类型注解后, 很多函数签名 (signature) 会变成每行一个参数的形式. 若要让返回值单独成行, 可以在最后一个参数尾部添加逗号.

```python
def my_method(
    self,
    first_var: int,
    second_var: Foo,
    third_var: Bar | None,
) -> int:
    ...
```

尽量在变量之间换行, 避免在变量和类型注解之间换行. 当然, 若所有东西可以挤进一行, 也可以接受.

```python
def my_method(self, first_var: int) -> int:
    ...
```

若最后一个参数加上返回值的类型注解太长, 也可以换行并添加4格缩进. 添加换行符时, 建议每个参数和返回值都在单独的一行里, 并且右括号和 `def` 对齐.

正确:

```python
def my_method(
    self,
    other_arg: MyLongType | None,
) -> tuple[MyLongType1, MyLongType1]:
    ...
```

返回值类型和最后一个参数也可以放在同一行.

可以接受:

```python
def my_method(
    self,
    first_var: int,
    second_var: int) -> dict[OtherLongType, MyLongType]:
    ...
```

`pylint` 也允许你把右括号放在新行上, 与左括号对齐, 但相较而言可读性更差.

错误:

```python
def my_method(self,
              other_arg: MyLongType | None,
             ) -> dict[OtherLongType, MyLongType]:
    ...
```

正如上面所有的例子, 尽量不要在类型注解中间换行. 但是有时注解过长以至于一行放不下. 此时尽量保持子类型中间不换行.

```python
def my_method(
    self,
    first_var: tuple[list[MyLongType1],
                     list[MyLongType2]],
    second_var: list[dict[
        MyLongType3, MyLongType4]],
) -> None:
    ...
```

若某个名称和对应的类型注解过长, 可以考虑用 别名 (alias)  代表类型. 下策是在冒号后换行并添加4格缩进.

正确:

```python
def my_function(
    long_variable_name:
        long_module_name.LongTypeName,
) -> None:
    ...
```

错误:

```python
def my_function(
    long_variable_name: long_module_name.
        LongTypeName,
) -> None:
    ...
```

**前向声明 (foward declaration)**

若需要使用一个尚未定义的类名 (比如想在声明一个类时使用自身的类名), 可以使用 `from __future__ import annotations` 或者字符串来代表类名.

正确:

```python
from __future__ import annotations

class MyClass:
    def __init__(self, stack: Sequence[MyClass], item: OtherClass) -> None:

class OtherClass:
    ...
```

```python
class MyClass:
    def __init__(self, stack: Sequence['MyClass'], item: 'OtherClass') -> None:

class OtherClass:
    ...
```

**默认值**

根据 [PEP-008 ](https://www.python.org/dev/peps/pep-0008/#other-recommendations) , **只有** 对于同时拥有类型注解和默认值的参数, `=` 的周围应该加空格.

正确:

```python
def func(a: int = 0) -> int:
    ...
```

错误:

```python
def func(a:int=0) -> int:
    ...
```

**NoneType**

在 Python 的类型系统中, `NoneType` 是 "一等" 类型. 在类型注解中, `None` 是 `NoneType` 的别名. 如果一个变量可能为 `None`, 则必须声明这种情况! 你可以使用 `|` 这样的并集 (union) 类型表达式 (推荐在新的 Python 3.10+ 代码中使用) 或者老的 `Optional` 和 `Union` 语法.

应该用显式的 `X | None` 替代隐式声明. 早期的 PEP 484 允许将 `a: str = None` 解释为 `a: str | None = None`, 但这不再是推荐的行为.

正确:

```python
# 现代的并集写法.
def modern_or_union(a: str | int | None, b: str | None = None) -> str:
    ...
# 采用 Union / Optional.
def union_optional(a: Union[str, int, None], b: Optional[str] = None) -> str:
    ...
```

错误:

```python
# 用 Union 代替 Optional.
def nullable_union(a: Union[None, str]) -> str:
    ...
# 隐式 Optional.
def implicit_optional(a: str = None) -> str:
    ...
```

**类型别名 (alias)**

你可以为复杂的类型声明一个别名. 别名的命名应该采用大驼峰 (例如 `CapWorded`). 若别名仅在当前模块使用, 应在名称前加 `_` 代表私有 (例如 `_Private`).

注意下面的 `: TypeAlias` 类型注解只能在 3.10 以后的版本使用.

```python
from typing import TypeAlias

_LossAndGradient: TypeAlias = tuple[tf.Tensor, tf.Tensor]
ComplexTFMap: TypeAlias = Mapping[str, _LossAndGradient]
```

**忽略类型**

你可以使用特殊的注释 `# type: ignore` 禁用某一行的类型检查.

`pytype` 有针对特定错误的禁用选项 (类似格式检查器):

```python
# pytype: disable=attribute-error
```

**标注变量的类型**

**带类型注解的赋值**

如果难以自动推理某个内部变量的类型, 可以用带类型注解的赋值操作来指定类型: 在变量名和值的中间添加冒号和类型, 类似于有默认值的函数参数.

```python
a: Foo = SomeUndecoratedFunction()
```

**类型注释**

你可能在代码仓库中看到这种残留的注释 (在 Python 3.6 之前必须这样写注释), 但是不要再添加 `# type: <类型>` 这样的行尾注释了:

```python
a = SomeUndecoratedFunction()  # type: Foo
```

**元组还是列表**

有类型的列表中只能有一种类型的元素. 有类型的元组可以有相同类型的元素或者若干个不同类型的元素. 后面这种情况多用于注解返回值的类型.

(译者注: 注意这里是指的类型注解中的写法,实际python中,list和tuple都是可以在一个序列中包含不同类型元素的,当然,本质其实list和tuple中放的是元素的引用)

```python
a: list[int] = [1, 2, 3]
b: tuple[int, ...] = (1, 2, 3)
c: tuple[int, str, float] = (1, "2", 3.5)
```

**类型变量 (type variable)**

Python 的类型系统支持 [泛型 (generics) ](https://peps.python.org/pep-0484/#generics) . 使用泛型的常见方式是利用类型变量, 例如 `TypeVar` 和 `ParamSpec`.

例如:

```python
from collections.abc import Callable
from typing import ParamSpec, TypeVar
_P = ParamSpec("_P")
_T = TypeVar("_T")
...
def next(l: list[_T]) -> _T:
    return l.pop()

def print_when_called(f: Callable[_P, _T]) -> Callable[_P, _T]:
    def inner(*args: P.args, **kwargs: P.kwargs) -> R:
        print('函数被调用')
        return f(*args, **kwargs)
return inner
```

`TypeVar` 可以有约束条件.

```python
AddableType = TypeVar("AddableType", int, float, str)
def add(a: AddableType, b: AddableType) -> AddableType:
    return a + b
```

`AnyStr` 是 `typing` 模块中常用的预定义类型变量. 可以用它注解那些接受 `bytes` 或 `str` 但是必须保持一致的类型.

```python
from typing import AnyStr
def check_length(x: AnyStr) -> AnyStr:
    if len(x) <= 42:
        return x
    raise ValueError()
```

(译者注: 这个例子中, x 和返回值必须同时是 `bytes` 或者同时是 `str`.)

类型变量必须有描述性的名称, 除非满足以下所有标准:

1. 外部不可见
1. 没有约束条件

正确:

```python
_T = TypeVar("_T")
_P = ParamSpec("_P")
AddableType = TypeVar("AddableType", int, float, str)
AnyFunction = TypeVar("AnyFunction", bound=Callable)
```

错误:

```python
T = TypeVar("T")
P = ParamSpec("P")
_T = TypeVar("_T", int, float, str)
_F = TypeVar("_F", bound=Callable)
```

**字符串类型**

不要在新代码中使用 `typing.Text`. 这种写法只能用于处理 Python 2/3 的兼容问题.

用 `str` 表示字符串/文本数据. 用 `bytes` 处理二进制数据.

```python
# 处理文本数据
def deals_with_text_data(x: str) -> str:
    ...
# 处理二进制数据
def deals_with_binary_data(x: bytes) -> bytes:
    ...
```

若一个函数中的字串类型始终一致, 比如上述代码中返回值类型和参数类型相同, 应该使用 [AnyStr ](https://google.github.io/styleguide/pyguide.html#typing-type-var).

**导入类型**

为了静态分析和类型检查而导入 `typing` 和 `collections.abc` 模块中的符号时, 一定要导入符号本身. 这样常用的类型注解更简洁, 也符合全世界的习惯. 特别地, 你可以在一行内从 `typing` 和 `collections.abc` 模块中导入多个特定的类, 例如:

```python
from collections.abc import Mapping, Sequence
from typing import Any, Generic
```

采用这种方法时, 导入的类会进入本地命名空间, 因此所有 `typing` 和 `collections.abc` 模块中的名称都应该和关键词 (keyword) 同等对待. 你不能在自己的代码中定义相同的名字, 无论你是否采用类型注解. 若类型名和某模块中已有的名称出现冲突, 可以用 `import x as y` 的导入形式:

```python
from typing import Any as AnyType
```

只要可行, 就使用内置类型. 利用 Python 3.9 引入的 [PEP-585 ](https://peps.python.org/pep-0585/), 可以在类型注解中使用参数化的容器类型.

```python
def generate_foo_scores(foo: set[str]) -> list[float]:
    ...
```

注意: [Apache Beam ](https://github.com/apache/beam/issues/23366) 的用户应该继续导入 `typing` 模块提供的参数化容器类型.

```python
from typing import Set, List

# 只有在你使用了 Apache Beam 这样没有为 PEP 585 更新的代码, 或者你的
# 代码需要在 Python 3.9 以下版本中运行时, 才能使用这种旧风格.
def generate_foo_scores(foo: Set[str]) -> List[float]:
    ...
```

**有条件的导入**

仅在一些特殊情况下, 比如在运行时必须避免导入类型检查所需的模块, 才能有条件地导入. 不推荐这种写法. 替代方案是重构代码, 使类型检查所需的模块可以在顶层导入.

可以把仅用于类型注解的导入放在 `if TYPE_CHECKING:` 语句块内.

1. 在类型注解中, 有条件地导入的类型必须用字符串表示, 这样才能和 Python 3.6 之前的代码兼容. 因为 Python 3.6 之前真的会对类型注解求值.
1. 只有那些仅仅用于类型注解的实例才能有条件地导入, 别名也是如此. 否则会引发运行时错误, 因为运行时不会导入这些模块.
1. 有条件的导入语句应紧随所有常规导入语句之后.
1. 有条件的导入语句之间不能有空行.
1. 和常规导入一样, 请对有条件的导入语句排序.

```python
import typing
if typing.TYPE_CHECKING:
    import sketch
def f(x: "sketch.Sketch"): ...
```

**循环依赖**

若类型注解引发了循环依赖, 说明代码可能存在问题. 这样的代码适合重构. 虽然技术上我们可以支持循环依赖, 但是很多构建系统 (build system) 不支持.

可以用 `Any` 替换引起循环依赖的模块. 起一个有意义的别名, 然后使用模块中的真实类型名 (Any 的任何属性依然是 Any). 定义别名的语句应该和最后一行导入语句之间间隔一行.

```python
from typing import Any

some_mod = Any  # 因为 some_mod.py 导入了我们的模块.
...

def my_method(self, var: "some_mod.SomeType") -> None:
    ...
```

**泛型 (generics)**

在注解类型时, 尽量为泛型类型填入类型参数. 否则, [泛型参数默认为 Any ](https://www.python.org/dev/peps/pep-0484/#the-any-type) .

正确:

```python
def get_names(employee_ids: Sequence[int]) -> Mapping[int, str]:
    ...
```

错误:

```python
# 这表示 get_names(employee_ids: Sequence[Any]) -> Mapping[Any, Any]
def get_names(employee_ids: Sequence) -> Mapping:
    ...
```

如果泛型类型的参数的确应该是 `Any`, 请显式地标注, 不过注意 `TypeVar` 很可能更合适.

错误:

```python
def get_names(employee_ids: Sequence[Any]) -> Mapping[Any, str]:
    """返回员工ID到员工名的映射."""
```

正确:

```python
_T = TypeVar('_T')
def get_names(employee_ids: Sequence[_T]) -> Mapping[_T, str]:
    """返回员工ID到员工名的映射."""
```

## 临别赠言

**务必保持一致性.**

编辑代码时, 请花几分钟观察一下周边代码的风格. 如果这些代码在所有运算符的周围加上了空格, 那么你也应该这样做. 如果这些代码的注释都用井号形成的框包围起来, 那么你的注释也要用井号形成的框包起来.

制定风格指南是为了像字典一样让代码有章可循. 这样人们可以专注于"写什么", 而不是纠结"怎么写". 我们在这里列出的全局规范就像字典, 但是局部的规范同样重要. 如果你添加的代码和周围原有的代码大相径庭, 就会打乱读者的阅读节奏. 不要这样.

---

## 开源许可证

本文件的上游内容依据 Apache License 2.0 发布。根据许可证的再分发要求，完整许可文本如下：

```text
Apache License
                           Version 2.0, January 2004
                        https://www.apache.org/licenses/

   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

   1. Definitions.

      "License" shall mean the terms and conditions for use, reproduction,
      and distribution as defined by Sections 1 through 9 of this document.

      "Licensor" shall mean the copyright owner or entity authorized by
      the copyright owner that is granting the License.

      "Legal Entity" shall mean the union of the acting entity and all
      other entities that control, are controlled by, or are under common
      control with that entity. For the purposes of this definition,
      "control" means (i) the power, direct or indirect, to cause the
      direction or management of such entity, whether by contract or
      otherwise, or (ii) ownership of fifty percent (50%) or more of the
      outstanding shares, or (iii) beneficial ownership of such entity.

      "You" (or "Your") shall mean an individual or Legal Entity
      exercising permissions granted by this License.

      "Source" form shall mean the preferred form for making modifications,
      including but not limited to software source code, documentation
      source, and configuration files.

      "Object" form shall mean any form resulting from mechanical
      transformation or translation of a Source form, including but
      not limited to compiled object code, generated documentation,
      and conversions to other media types.

      "Work" shall mean the work of authorship, whether in Source or
      Object form, made available under the License, as indicated by a
      copyright notice that is included in or attached to the work
      (an example is provided in the Appendix below).

      "Derivative Works" shall mean any work, whether in Source or Object
      form, that is based on (or derived from) the Work and for which the
      editorial revisions, annotations, elaborations, or other modifications
      represent, as a whole, an original work of authorship. For the purposes
      of this License, Derivative Works shall not include works that remain
      separable from, or merely link (or bind by name) to the interfaces of,
      the Work and Derivative Works thereof.

      "Contribution" shall mean any work of authorship, including
      the original version of the Work and any modifications or additions
      to that Work or Derivative Works thereof, that is intentionally
      submitted to Licensor for inclusion in the Work by the copyright owner
      or by an individual or Legal Entity authorized to submit on behalf of
      the copyright owner. For the purposes of this definition, "submitted"
      means any form of electronic, verbal, or written communication sent
      to the Licensor or its representatives, including but not limited to
      communication on electronic mailing lists, source code control systems,
      and issue tracking systems that are managed by, or on behalf of, the
      Licensor for the purpose of discussing and improving the Work, but
      excluding communication that is conspicuously marked or otherwise
      designated in writing by the copyright owner as "Not a Contribution."

      "Contributor" shall mean Licensor and any individual or Legal Entity
      on behalf of whom a Contribution has been received by Licensor and
      subsequently incorporated within the Work.

   2. Grant of Copyright License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      copyright license to reproduce, prepare Derivative Works of,
      publicly display, publicly perform, sublicense, and distribute the
      Work and such Derivative Works in Source or Object form.

   3. Grant of Patent License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      (except as stated in this section) patent license to make, have made,
      use, offer to sell, sell, import, and otherwise transfer the Work,
      where such license applies only to those patent claims licensable
      by such Contributor that are necessarily infringed by their
      Contribution(s) alone or by combination of their Contribution(s)
      with the Work to which such Contribution(s) was submitted. If You
      institute patent litigation against any entity (including a
      cross-claim or counterclaim in a lawsuit) alleging that the Work
      or a Contribution incorporated within the Work constitutes direct
      or contributory patent infringement, then any patent licenses
      granted to You under this License for that Work shall terminate
      as of the date such litigation is filed.

   4. Redistribution. You may reproduce and distribute copies of the
      Work or Derivative Works thereof in any medium, with or without
      modifications, and in Source or Object form, provided that You
      meet the following conditions:

      (a) You must give any other recipients of the Work or
          Derivative Works a copy of this License; and

      (b) You must cause any modified files to carry prominent notices
          stating that You changed the files; and

      (c) You must retain, in the Source form of any Derivative Works
          that You distribute, all copyright, patent, trademark, and
          attribution notices from the Source form of the Work,
          excluding those notices that do not pertain to any part of
          the Derivative Works; and

      (d) If the Work includes a "NOTICE" text file as part of its
          distribution, then any Derivative Works that You distribute must
          include a readable copy of the attribution notices contained
          within such NOTICE file, excluding those notices that do not
          pertain to any part of the Derivative Works, in at least one
          of the following places: within a NOTICE text file distributed
          as part of the Derivative Works; within the Source form or
          documentation, if provided along with the Derivative Works; or,
          within a display generated by the Derivative Works, if and
          wherever such third-party notices normally appear. The contents
          of the NOTICE file are for informational purposes only and
          do not modify the License. You may add Your own attribution
          notices within Derivative Works that You distribute, alongside
          or as an addendum to the NOTICE text from the Work, provided
          that such additional attribution notices cannot be construed
          as modifying the License.

      You may add Your own copyright statement to Your modifications and
      may provide additional or different license terms and conditions
      for use, reproduction, or distribution of Your modifications, or
      for any such Derivative Works as a whole, provided Your use,
      reproduction, and distribution of the Work otherwise complies with
      the conditions stated in this License.

   5. Submission of Contributions. Unless You explicitly state otherwise,
      any Contribution intentionally submitted for inclusion in the Work
      by You to the Licensor shall be under the terms and conditions of
      this License, without any additional terms or conditions.
      Notwithstanding the above, nothing herein shall supersede or modify
      the terms of any separate license agreement you may have executed
      with Licensor regarding such Contributions.

   6. Trademarks. This License does not grant permission to use the trade
      names, trademarks, service marks, or product names of the Licensor,
      except as required for reasonable and customary use in describing the
      origin of the Work and reproducing the content of the NOTICE file.

   7. Disclaimer of Warranty. Unless required by applicable law or
      agreed to in writing, Licensor provides the Work (and each
      Contributor provides its Contributions) on an "AS IS" BASIS,
      WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
      implied, including, without limitation, any warranties or conditions
      of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
      PARTICULAR PURPOSE. You are solely responsible for determining the
      appropriateness of using or redistributing the Work and assume any
      risks associated with Your exercise of permissions under this License.

   8. Limitation of Liability. In no event and under no legal theory,
      whether in tort (including negligence), contract, or otherwise,
      unless required by applicable law (such as deliberate and grossly
      negligent acts) or agreed to in writing, shall any Contributor be
      liable to You for damages, including any direct, indirect, special,
      incidental, or consequential damages of any character arising as a
      result of this License or out of the use or inability to use the
      Work (including but not limited to damages for loss of goodwill,
      work stoppage, computer failure or malfunction, or any and all
      other commercial damages or losses), even if such Contributor
      has been advised of the possibility of such damages.

   9. Accepting Warranty or Additional Liability. While redistributing
      the Work or Derivative Works thereof, You may choose to offer,
      and charge a fee for, acceptance of support, warranty, indemnity,
      or other liability obligations and/or rights consistent with this
      License. However, in accepting such obligations, You may act only
      on Your own behalf and on Your sole responsibility, not on behalf
      of any other Contributor, and only if You agree to indemnify,
      defend, and hold each Contributor harmless for any liability
      incurred by, or claims asserted against, such Contributor by reason
      of your accepting any such warranty or additional liability.

   END OF TERMS AND CONDITIONS

   APPENDIX: How to apply the Apache License to your work.

      To apply the Apache License to your work, attach the following
      boilerplate notice, with the fields enclosed by brackets "[]"
      replaced with your own identifying information. (Don't include
      the brackets!)  The text should be enclosed in the appropriate
      comment syntax for the file format. We also recommend that a
      file or class name and description of purpose be included on the
      same "printed page" as the copyright notice for easier
      identification within third-party archives.

   Copyright [yyyy] [name of copyright owner]

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       https://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
```
