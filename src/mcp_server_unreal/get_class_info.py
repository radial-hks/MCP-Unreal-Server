import inspect
import unreal
import json
import re

def get_type_from_docstring(doc):
    """尝试从文档字符串中提取类型信息 (例如 '(Vector):')"""
    if not doc:
        return "Unknown"
    match = re.search(r"\(([\w\.]+)\):", doc)
    return match.group(1) if match else "Unknown"

def get_editor_properties_from_docstring(doc):
    """尝试从类文档字符串中提取 Editor Properties"""
    props = []
    if not doc:
        return props
    editor_props_section = re.search(r"\*\*Editor Properties:\*\*.*?\n(.*?)\n\n", doc, re.DOTALL)
    if editor_props_section:
        prop_lines = editor_props_section.group(1).strip().split('\n')
        for line in prop_lines:
            line = line.strip()
            if line.startswith('- ``'):
                match = re.search(r"- ``(.*?)`` \((.*?)\):", line)
                if match:
                    props.append([match.group(1), match.group(2)])
    return props


def inspect_class_to_json(cls):
    info = {
        "children": [],  # 需要分析整个代码库才能确定
        "class_methods": [],
        "editor_properties": [], # 尝试从文档字符串提取
        "generation": 0, # inspect 无法直接获取此信息
        "grand_parent": None,
        "methods": [],
        "name": cls.__name__,
        "parent": None,
        "parents": [],
        "properties": [],
        "referenced_by": {}, # 需要分析整个代码库才能确定
        "references": {}, # 需要更复杂的类型提示或文档字符串解析
        "static_methods": []
    }

    # 获取继承层次
    mro = inspect.getmro(cls)
    info["parents"] = [base.__name__ for base in mro[1:]] # Exclude self
    if len(mro) > 1:
        info["parent"] = mro[1].__name__
    if len(mro) > 2:
         # 假设 _WrapperBase 是通用基类，查找它
         wrapper_base_found = False
         for base in reversed(mro):
             if base.__name__ == '_WrapperBase':
                 info["grand_parent"] = base.__name__
                 wrapper_base_found = True
                 break
         # 如果找不到 _WrapperBase，则取继承链中的倒数第二个作为祖父类（如果存在）
         if not wrapper_base_found and len(mro) > 2:
             info["grand_parent"] = mro[-2].__name__ # Fallback

    # 尝试从类文档字符串提取 Editor Properties
    class_doc = inspect.getdoc(cls)
    info["editor_properties"] = get_editor_properties_from_docstring(class_doc)


    # 获取属性和方法
    references_count = {}
    processed_members = set()

    for i in inspect.classify_class_attrs(cls):
         # 跳过继承来的成员，只处理当前类定义的
        if i.defining_class != cls:
             continue
         # 跳过特殊方法和私有方法，除非是 __init__
        if i.name.startswith('_') and i.name != '__init__':
             continue
        # 跳过已处理的成员 (例如 property 的 fget/fset/fdel)
        if i.name in processed_members:
            continue

        member_type = "Unknown"
        member_obj = None
        try:
            member_obj = getattr(cls, i.name)
        except AttributeError:
            continue # Skip if attribute cannot be accessed

        if i.kind == "property":
            info["properties"].append(i.name)
            processed_members.add(i.name)
            # 尝试获取属性类型
            prop_doc = inspect.getdoc(member_obj)
            member_type = get_type_from_docstring(prop_doc)

        elif i.kind == "method":
            info["methods"].append(i.name)
            processed_members.add(i.name)
            member_type = "method" # 方法本身类型
            # 分析方法签名以查找引用的类型
            try:
                sig = inspect.signature(member_obj)
                # 参数类型
                for param in sig.parameters.values():
                    if param.annotation != inspect.Parameter.empty and hasattr(param.annotation, '__name__'):
                         ref_name = param.annotation.__name__
                         references_count[ref_name] = references_count.get(ref_name, 0) + 1
                # 返回类型
                if sig.return_annotation != inspect.Signature.empty and hasattr(sig.return_annotation, '__name__'):
                     ref_name = sig.return_annotation.__name__
                     references_count[ref_name] = references_count.get(ref_name, 0) + 1
            except (ValueError, TypeError): # 可能无法获取某些内置或C扩展方法的签名
                pass


        elif i.kind == "class method":
            info["class_methods"].append(i.name)
            processed_members.add(i.name)
            member_type = "class method"
        elif i.kind == "static method":
            info["static_methods"].append(i.name)
            processed_members.add(i.name)
            member_type = "static method"

        # 更新引用计数 (基于属性类型)
        if member_type != "Unknown" and member_type not in ["method", "class method", "static method"]:
             references_count[member_type] = references_count.get(member_type, 0) + 1


    # 添加父类的引用
    if info["parent"]:
        references_count[info["parent"]] = references_count.get(info["parent"], 0) + 1

    info["references"] = references_count

    # 清理空列表
    info = {k: v for k, v in info.items() if v or k in ["name", "generation", "children", "referenced_by"]} # 保留特定空字段

    return json.dumps(info, indent=2)


# 调用函数并打印 JSON
json_output = inspect_class_to_json(unreal.Box)
print(json_output)

# 预期从 unreal.Box 提取的 JSON (基于您提供的目标和 inspect 能力)
# 注意: referenced_by 和 children 无法仅通过 inspect 单个类来确定
# 注意: editor_properties 和 references 的提取依赖于文档字符串格式
"""
预期输出示例 (可能因 unreal.py stub 的实际内容和格式略有不同):
{
  "children": [],
  "class_methods": [],
  "editor_properties": [
    [
      "is_valid",
      "bool"
    ],
    [
      "max",
      "Vector"
    ],
    [
      "min",
      "Vector"
    ]
  ],
  "generation": 0,
  "grand_parent": "_WrapperBase",
  "methods": [
    "__init__",
    "random_point_in_box_extents",
    "test_point_inside_box",
    "test_box_sphere_intersection"
  ],
  "name": "Box",
  "parent": "StructBase",
  "parents": [
    "StructBase",
    "_WrapperBase",
    "object"
  ],
  "properties": [
    "is_valid",
    "max",
    "min"
  ],
  "referenced_by": {},
  "references": {
    "StructBase": 1,
    "Vector": 7, # __init__ min, max, random_point_in_box_extents ret, test_point_inside_box point, test_box_sphere_intersection center, prop max, prop min
    "bool": 3,   # __init__ consider_on_box_as_inside, test_point_inside_box ret, prop is_valid
    "float": 1   # test_box_sphere_intersection radius (assuming double maps to float)
  },
  "static_methods": []
}
"""