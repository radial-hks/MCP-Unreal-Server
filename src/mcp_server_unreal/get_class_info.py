import inspect
import importlib
import unreal # Keep the direct import for potential type hinting or fallback
import json
import re
import sys

def get_type_from_docstring(doc):
    """尝试从文档字符串中提取类型信息 (例如 '(Vector):')"""
    if not doc:
        return "Unknown"
    # 匹配 '(Type):' 或 '[Read-Write]' 后面的类型
    match = re.search(r"\(([\w\.]+)\):", doc)
    if match:
        return match.group(1)
    match_rw = re.search(r"\[Read-Write\]\s*\(([\w\.]+)\)", doc)
    if match_rw:
        return match_rw.group(1)
    return "Unknown"

def get_editor_properties_from_docstring(doc):
    """尝试从类文档字符串中提取 Editor Properties"""
    props = []
    if not doc:
        return props
    # 使用更健壮的正则匹配 Editor Properties 部分
    editor_props_section = re.search(r"\*\*Editor Properties:\*\*\s*\(see get_editor_property/set_editor_property\)\s*\n(.*?)(?=\n\n|\Z)", doc, re.DOTALL | re.IGNORECASE)
    if editor_props_section:
        prop_lines = editor_props_section.group(1).strip().split('\n')
        for line in prop_lines:
            line = line.strip()
            # 匹配 '- ``prop_name`` (type):' 格式
            match = re.search(r"-\s*``(.*?)``\s*\((.*?)\):", line)
            if match:
                prop_name = match.group(1).strip()
                prop_type = match.group(2).strip()
                # 避免重复添加相同的属性名
                if not any(p[0] == prop_name for p in props):
                    props.append([prop_name, prop_type])
    return props


def inspect_class_to_json(cls):
    """为单个类生成结构化的 JSON 信息"""
    info = {
        "children": [],
        "class_methods": [],
        "editor_properties": [],
        "generation": 0,
        "grand_parent": None,
        "methods": [],
        "name": cls.__name__,
        "parent": None,
        "parents": [],
        "properties": [],
        "referenced_by": {},
        "references": {},
        "static_methods": []
    }

    try:
        mro = inspect.getmro(cls)
        info["parents"] = [base.__name__ for base in mro[1:]]
        if len(mro) > 1:
            info["parent"] = mro[1].__name__
        if len(mro) > 2:
            # 查找 _WrapperBase 或 object 之前的最后一个作为祖父类
            grand_parent_index = -1
            for i in range(len(mro) - 1, 1, -1):
                if mro[i].__name__ not in ('object', '_WrapperBase'):
                    grand_parent_index = i
                    break
                elif mro[i].__name__ == '_WrapperBase' and i > 1: # Prefer _WrapperBase if not direct parent
                    grand_parent_index = i
                    break

            if grand_parent_index != -1 and grand_parent_index < len(mro) -1 :
                # Ensure grand_parent is not the direct parent if possible
                actual_grand_parent_index = grand_parent_index
                if mro[grand_parent_index] == mro[1]: # If calculated grand_parent is the parent
                    if grand_parent_index + 1 < len(mro) and mro[grand_parent_index+1].__name__ != 'object':
                        actual_grand_parent_index = grand_parent_index + 1
                    elif grand_parent_index > 1: # Fallback to parent's parent if exists
                        actual_grand_parent_index = 2


                if actual_grand_parent_index < len(mro):
                    info["grand_parent"] = mro[actual_grand_parent_index].__name__


        class_doc = inspect.getdoc(cls)
        # 获取类的注释部分
        # print(class_doc)
        info["editor_properties"] = get_editor_properties_from_docstring(class_doc)

        references_count = {}
        processed_members = set()

        # 使用 classify_class_attrs 获取并分类当前类定义的成员
        for attr in inspect.classify_class_attrs(cls):
            # print(attr.defining_class)
            
            # 只处理当前类定义的成员
            if attr.defining_class != cls:
                continue

            # 跳过特殊方法和私有方法，除非是 __init__
            if attr.name.startswith('_') and attr.name != '__init__':
                continue
            # print(f"  {attr.name}:{attr.kind}:{attr.defining_class}")
            member_obj = attr.object # 获取成员对象

            if attr.kind == "property":
                info["properties"].append(attr.name)
                prop_doc = inspect.getdoc(member_obj)
                # 假设 get_type_from_docstring 函数存在且可用
                member_type_str = get_type_from_docstring(prop_doc)
                if member_type_str != "Unknown":
                    references_count[member_type_str] = references_count.get(member_type_str, 0) + 1
            elif attr.kind == "class method":
                info["class_methods"].append(attr.name)
                # 注意：原始代码未对类方法或静态方法进行签名分析以查找引用
                # 如果需要，可以在此处添加类似方法的签名分析逻辑

            elif attr.kind == "static method":
                info["static_methods"].append(attr.name)
            elif attr.kind == "method":
                info["methods"].append(attr.name)
                # 分析签名以查找引用 (与原始代码逻辑保持一致)
                try:
                    # 对于方法，attr.object 通常是函数本身
                    sig = inspect.signature(member_obj)
                    for param in sig.parameters.values():
                        if param.annotation != inspect.Parameter.empty and hasattr(param.annotation, '__name__'):
                            ref_name = param.annotation.__name__
                            references_count[ref_name] = references_count.get(ref_name, 0) + 1
                    if sig.return_annotation != inspect.Signature.empty and hasattr(sig.return_annotation, '__name__'):
                        ref_name = sig.return_annotation.__name__
                        references_count[ref_name] = references_count.get(ref_name, 0) + 1
                except (ValueError, TypeError):
                    # 如果无法获取签名（例如，某些内置方法），则忽略
                    pass
            # 可以选择性地处理 'data' 类型的属性
            # elif attr.kind == "data":
            #     if "attributes" not in info: info["attributes"] = []
            #     info["attributes"].append(attr.name)
            #     # 可以在这里添加对数据属性类型注解的分析逻辑
            #     annotations = getattr(cls, '__annotations__', {})
            #     if attr.name in annotations:
            #         annotation = annotations[attr.name]
            #         if hasattr(annotation, '__name__'):
            #              ref_name = annotation.__name__
            #              references_count[ref_name] = references_count.get(ref_name, 0) + 1

        # 注意: 使用 classify_class_attrs 和 defining_class 检查后，
        # 'processed_members' 集合通常不再需要，因为它能正确处理继承和覆盖。

        # Add parent reference
        if info["parent"]:
            references_count[info["parent"]] = references_count.get(info["parent"], 0) + 1

        info["references"] = references_count
        info = {k: v for k, v in info.items() if v or k in ["name", "generation", "children", "referenced_by"]}

    except Exception as e:
        print(f"Error inspecting class {cls.__name__}: {e}")
        # Return basic info on error
        return json.dumps({"name": cls.__name__, "error": str(e)}, indent=2)
    # print(info)
    return json.dumps(info, indent=2)


def get_module_classes(module_name):
    """动态导入模块并获取其中定义的类"""
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        print(f"错误：无法导入模块 '{module_name}'。")
        return []
    # print("断点测试---1")
    # print(module)
    classes = []
    for name, obj in inspect.getmembers(module, inspect.isclass):
        # print(name)
        # 确保类是在当前模块中定义的 (或其子模块，对 unreal 可能需要)
        # if hasattr(obj, '__module__') and obj.__module__ is not None and obj.__module__.startswith(module_name):
            # 进一步检查，避免导入第三方库的类，如果需要的话
            # if 'unreal' in str(obj.__module__): # Example filter
        classes.append((name, obj))
        # print("断点测试---2")
    return classes

if __name__ == "__main__":
    module_to_inspect = "unreal"
    # print(f"Inspecting module: {module_to_inspect}")
    class_list = get_module_classes(module_to_inspect)[1:]
    all_class_info = {}

    # class_json_str = inspect_class_to_json(unreal.Box)
    # print(class_json_str)
    
    if class_list:
        # print(f"Found {len(class_list)} classes in module '{module_to_inspect}'. Generating JSON...")
        # 使用字典来存储所有类的 JSON 信息，以类名为键
        for name, cls_obj in class_list:
            # print("断点测试---3")
            # print(f"Processing: {name}")
            # if name == "Box":
            class_json_str = inspect_class_to_json(cls_obj)
            try:
                # 解析单个类的 JSON 以便合并
                all_class_info[name] = json.loads(class_json_str)
            except json.JSONDecodeError:
                print(f"Warning: Could not decode JSON for class {name}")
                all_class_info[name] = {"name": name, "error": "JSON Decode Error"}
        # 打印包含所有类信息的单个 JSON 对象
        print(json.dumps(all_class_info, indent=2))
    else:
        print(f"No classes found in module '{module_to_inspect}'.")