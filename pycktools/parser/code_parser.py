import astroid
import json

from utils.json_utils import SetEncoder

class CodeParser:

    _CLASS_INIT = {
        'accessed_attributes': set(),
        'called': set(),
        'methods': {},
        'attributes': set(),
        'variables': set(),
        'direct_children': 0,
        'coupled_classes': set()
    }

    _METHOD_INIT = {
        'accessed_attributes': set(),
        'called': set(),
        'lloc': 0,
        'number_of_parameters': 0,
    }
    
    def __init__(self) -> None:

        self.classes = {}
        self.inheritances = {}

    def count_lloc(self, node):
        """
        Count the number of logical lines of code in the given AST node.
        """
        if not isinstance(node, (astroid.FunctionDef, astroid.AsyncFunctionDef)):
            raise ValueError("Node must be a function or method definition")
        
        lloc = 0
        for child in node.body:
            if isinstance(child, (
                astroid.Assign, astroid.AugAssign, astroid.AnnAssign, astroid.Expr, astroid.Return,
                astroid.Raise, astroid.Delete, astroid.Pass, astroid.Break, astroid.Continue,
                astroid.Global, astroid.Nonlocal, astroid.Assert, astroid.Import, astroid.ImportFrom
            )):
                lloc += 1
            elif isinstance(child, (astroid.If, astroid.For, astroid.While, astroid.Try, astroid.With)):
                lloc += self.count_lloc_in_compound_statement(child)
        return lloc

    def count_lloc_in_compound_statement(self, node):
        """
        Recursively count the logical lines of code in compound statements like if, for, while, try, with.
        """
        lloc = 1  # Count the compound statement itself
        for child in node.body:
            if isinstance(child, (
                astroid.Assign, astroid.AugAssign, astroid.AnnAssign, astroid.Expr, astroid.Return,
                astroid.Raise, astroid.Delete, astroid.Pass, astroid.Break, astroid.Continue,
                astroid.Global, astroid.Nonlocal, astroid.Assert, astroid.Import, astroid.ImportFrom
            )):
                lloc += 1
            elif isinstance(child, (astroid.If, astroid.For, astroid.While, astroid.Try, astroid.With)):
                lloc += self.count_lloc_in_compound_statement(child)
        for child in getattr(node, 'orelse', []):
            if isinstance(child, (
                astroid.Assign, astroid.AugAssign, astroid.AnnAssign, astroid.Expr, astroid.Return,
                astroid.Raise, astroid.Delete, astroid.Pass, astroid.Break, astroid.Continue,
                astroid.Global, astroid.Nonlocal, astroid.Assert, astroid.Import, astroid.ImportFrom
            )):
                lloc += 1
            elif isinstance(child, (astroid.If, astroid.For, astroid.While, astroid.Try, astroid.With)):
                lloc += self.count_lloc_in_compound_statement(child)
        return lloc
    
    def _extract_used_attributes_recursive(self, node, dict, class_name) -> None:
        """
        Recursively traverse the node and extract the methods that are called and the attributes that are accessed. 
        The extracted data is stored in the given dictionary.
        """
        if isinstance(node, astroid.Call):
            if node.args:
                for arg in node.args:
                    self._extract_used_attributes_recursive(arg, dict, class_name)
            called_method = node.func.as_string()
            dict['called'].add(called_method)
            if '.' in called_method:
                callee_class = called_method.split('.')[0]
                if callee_class != class_name:
                    self.classes[class_name]['coupled_classes'].add(callee_class)
        if isinstance(node, astroid.Attribute):
            attr_name = node.attrname
            if node.expr.as_string() != 'self':
                used_class = node.expr.as_string()
                self.classes[class_name]['coupled_classes'].add(used_class)
                attr_name = used_class + '.' + attr_name
            dict['accessed_attributes'].add(attr_name)

    def _extract_self_attributes(self, node, dict, class_name) -> None:
        """
        Extract the attributes of the class that are accessed via the 'self' variable
          from the given node and store the extracted data in the given dictionary.
        """
        for target in node.targets:
            if isinstance(target, astroid.AssignAttr):
                attr_name = target.attrname
                attr_instance = next(target.infer(), None).pytype()
                if attr_instance is astroid.Uninferable:
                    attr_instance = None
                else:
                    if attr_instance[0] == '.':
                        attr_instance = attr_instance[1:]
                self.classes[class_name]['attributes'].add((
                    attr_name, attr_instance
                ))
                dict['accessed_attributes'].add(attr_name)
        
    def _extract_methods(self, node: astroid.FunctionDef, class_name: str) -> None:
        
        """
        Extract the methods of the class from the given node and store the extracted data in the 
        classes dictionary.

        The extracted data includes the name of the method, the logical lines of code (LLOC), the number of
        parameters, the attributes that are accessed and the methods that are called.
        """
        method_name = node.name
        method_dict = self._METHOD_INIT
        method_dict['lloc'] = self.count_lloc(node)
        method_dict['number_of_parameters'] = len(node.args.args)
        
        for method_node in node.body:
            if isinstance(method_node, astroid.Assign):
                self._extract_self_attributes(method_node, method_dict, class_name)
            
            if isinstance(method_node, (astroid.Expr, astroid.Assign)):
                self._extract_used_attributes_recursive(
                    method_node.value, method_dict, class_name
                )

        self.classes[class_name]['methods'][method_name] = method_dict
                            
    def _extract_inheritance(self, base: astroid.FunctionDef, class_name: str) -> None:
        base_class = base.name
        self.inheritances[class_name] = base_class
        if base_class in self.classes:
            self.classes[base_class]['direct_children'] += 1

    def _extract_classes_data(self, module: astroid.Module) -> None:
        
        for node in module.body:
            if isinstance(node, astroid.ClassDef):
                class_name = node.name
                self.classes[class_name] = self._CLASS_INIT

                # Extract methods and attributes
                for class_node in node.body:

                    # Method instantiation
                    if isinstance(class_node, astroid.FunctionDef):
                        self._extract_methods(class_node, class_name)

                    # Attribute assign
                    if isinstance(class_node, astroid.Assign):
                        for target in class_node.targets:
                            attr_name = target.name
                            self.classes[class_name]['variables'].add(attr_name)
                            
                    # Method call or attribute access
                    if isinstance(class_node, (astroid.Expr, astroid.Assign)):
                        self._extract_used_attributes_recursive(
                            class_node.value, class_node, class_name
                        )

                # Extract inheritance information
                for base in node.bases:
                    if isinstance(base, astroid.Name):
                        self._extract_inheritance(base, class_name)

    def _translate_attributes_to_classes(self) -> None:
        pass
        # for class_name, class_data in self.classes.items():
        #     for method, method_data in class_data['methods'].items():
        #         for attr in method_data['accessed_attrigutes']:
        #             if attr in self.classes.keys():
        #                 self.classes[class_name]['coupled_classes'].add(attr_type)

    def extract_code_data(self, code: str) -> None:
        
        module = astroid.parse(code)

        self._extract_classes_data(module)
        self._translate_attributes_to_classes()


# Test execution
if __name__ == "__main__":
    cp = CodeParser()
    cp.extract_code_data(r"""
                                   
        class UsedClass:
            def __init__(self):
                self.used_attr_1 = 'I am here to be used!'
                self.used_attr_2 = 'I am here to be used!'
                self.used_attr_3 = UsedClass()
        
        class MySuperParent:
            super_parent_var = 0

            def __init__(self):
                pass
                
        class MyParent(MySuperParent):
            parent_var = 0

            def __init__(self):
                pass

        class MyClass(MyParent):
            class_variable = UsedClass6()

            def __init__(self, value: str):
                self.instance_variable = value
                self.UsedClassAttribute = UsedClass()
                usedClassVariable = UsedClass()

            def my_method(self):
                print(self.instance_variable)
                print(self.UsedClassAttribute.used_attr)
                print(self.UsedClassAttribute.used_attr_2, self.UsedClassAttribute.used_attr_3)

        def my_function():
            local_variable = 10
            print(local_variable)

    """)
    
    print('')
    print(json.dumps(cp.classes, cls=SetEncoder))
    print(json.dumps(cp.inheritances, cls=SetEncoder))