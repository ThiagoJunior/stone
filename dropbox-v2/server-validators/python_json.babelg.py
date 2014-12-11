"""
BabelAPI Code Generator for the Dropbox Python v2 SDK.

TODO: With a little bit more abstraction and better modularity, this could
become the general "Babel-Python" generator, and wouldn't have to be Dropbox-
specific at all.
"""

import re
from babelapi.data_type import (
    Int32,
    Int64,
    String,
    UInt32,
    UInt64,
)
from babelapi.data_type import (
    is_any_type,
    is_binary_type,
    is_boolean_type,
    is_composite_type,
    is_integer_type,
    is_list_type,
    is_null_type,
    is_string_type,
    is_struct_type,
    is_symbol_type,
    is_timestamp_type,
    is_union_type,
)
from babelapi.generator.generator import CodeGeneratorMonolingual
from babelapi.lang.python import PythonTargetLanguage

base = """\
import babel_data_types as dt

"""

# Matches format of Babel doc tags
doc_sub_tag_re = re.compile(':(?P<tag>[A-z]*):`(?P<val>.*?)`')

class PythonSDKGenerator(CodeGeneratorMonolingual):
    """Generates Python modules for the Dropbox Python v2 SDK that implement
    the data types defined in the spec."""

    lang = PythonTargetLanguage()

    def generate(self):
        """
        Generates a module for each namespace.

        Each namespace will have Python classes to represent structs and unions
        in the Babel spec. The namespace will also have a class of the same
        name but prefixed with "Base" that will have methods that represent
        the routes specified in the Babel spec.
        """
        for namespace in self.api.namespaces.values():
            with self.output_to_relative_path('{}.py'.format(namespace.name)):
                self._generate_base_namespace_module(namespace)

    def _generate_base_namespace_module(self, namespace):
        """Creates a module for the namespace. All data types are represented
        as classes."""
        self.emit(base)
        for data_type in namespace.linearize_data_types():
            if is_struct_type(data_type):
                self._generate_struct_class(data_type)
            elif is_union_type(data_type):
                self._generate_union_class(data_type)
            else:
                raise TypeError('Cannot handle type %r' % type(data_type))
        for route in namespace.routes:
            self._generate_route_class(namespace, route)

    def emit_wrapped_indented_lines(self, s):
        """Emits wrapped lines. All lines are the first are indented."""
        self.emit_wrapped_lines(s,
                                prefix='    ',
                                first_line_prefix=False)

    def docf(self, doc):
        """
        Substitutes tags in Babel docs with their Python-doc-friendly
        counterparts. A tag has the following format:

        :<tag>:`<value>`

        Example tags are 'route' and 'struct'.
        """
        if not doc:
            return
        for match in doc_sub_tag_re.finditer(doc):
            matched_text = match.group(0)
            tag = match.group('tag')
            val = match.group('val')
            if tag == 'struct':
                doc = doc.replace(matched_text, ':class:`{}`'.format(val))
            elif tag == 'route':
                doc = doc.replace(matched_text, val)
            elif tag == 'link':
                anchor, link = val.rsplit(' ', 1)
                doc = doc.replace(matched_text, '`{} <{}>`_'.format(anchor, link))
            elif tag == 'val':
                doc = doc.replace(matched_text, '{}'.format(self.lang.format_obj(val)))
            else:
                doc = doc.replace(matched_text, '``{}``'.format(val))
        return doc

    #
    # Struct Types
    #

    def _generate_struct_class(self, data_type):
        """Defines a Python class that represents a struct in Babel."""
        self.emit_line(self._class_declaration_for_data_type(data_type))
        with self.indent():
            if data_type.doc:
                self.emit_line('"""')
                self.emit_wrapped_lines(self.docf(data_type.doc))
                self.emit_empty_line()
                for field in data_type.fields:
                    if field.doc:
                        self.emit_wrapped_indented_lines(':ivar {}: {}'.format(
                            self.lang.format_variable(field.name),
                            self.docf(field.doc),
                        ))
                self.emit_line('"""')
            self.emit_empty_line()

            self._generate_struct_class_slots(data_type)
            self._generate_struct_class_vars(data_type)
            self._generate_struct_class_init(data_type)
            self._generate_struct_class_properties(data_type)
            self._generate_struct_class_repr(data_type)

    def _format_type_in_doc(self, data_type):
        if is_null_type(data_type):
            return 'None'
        elif is_composite_type(data_type):
            return ':class:`{}`'.format(self.lang.format_type(data_type))
        else:
            return self.lang.format_type(data_type)

    def _func_args_from_dict(self, d):
        filtered_d = self._filter_out_none_valued_keys(d)
        return ', '.join(['%s=%s' % (k, v) for k, v in filtered_d.items()])

    def _generate_struct_class_slots(self, data_type):
        self.emit_line('__slots__ = [')
        with self.indent():
            for field in data_type.fields:
                field_name = self.lang.format_variable(field.name)
                self.emit_line("'_%s'," % field_name)
                self.emit_line("'__has_%s'," % field_name)
        self.emit_line(']')
        self.emit_empty_line()

    def _generate_struct_class_vars(self, data_type):
        """
        Each class has a class attribute for each field that is a primitive type.
        The attribute is a validator for the field.
        """
        lineno = self.lineno
        for field in data_type.fields:
            field_name = self.lang.format_variable(field.name)
            validator_name = self._determine_validator_type(field.data_type)
            self.emit_line('__{}_data_type = {}'.format(field_name,
                                                        validator_name))
        if lineno != self.lineno:
            self.emit_empty_line()

        self._generate_fields_for_reflection(data_type)

    def _determine_validator_type(self, data_type):
        """
        FIXME: Add docs
        """
        if is_list_type(data_type):
            return 'dt.List({})'.format(
                self._func_args_from_dict({
                    'data_type': self._determine_validator_type(data_type.data_type),
                    'min_length': data_type.min_items,
                    'max_length': data_type.max_items,
                })
            )
        elif is_integer_type(data_type):
            return 'dt.{}({})'.format(
                data_type.name,
                self._func_args_from_dict({
                    'min_value': data_type.min_value,
                    'max_value': data_type.max_value,
                })
            )
        elif is_string_type(data_type):
            return 'dt.String({})'.format(
                self._func_args_from_dict({
                    'min_length': data_type.min_length,
                    'max_length': data_type.max_length,
                    'pattern': repr(data_type.pattern),
                })
            )
        elif is_timestamp_type(data_type):
            return 'dt.Timestamp({})'.format(
                self._func_args_from_dict({
                    'format': repr(data_type.format),
                })
            )
        elif is_struct_type(data_type):
            return 'dt.Struct({})'.format(
                self.lang.format_class(data_type.name),
            )
        elif is_union_type(data_type):
            class_name = self._class_name_for_data_type(data_type)
            return 'dt.Union({})'.format(
                self.lang.format_class(data_type.name),
            )
        else:
            return 'dt.{}()'.format(
                data_type.name,
            )

    def _generate_fields_for_reflection(self, data_type):
        if data_type.super_type:
            super_type_class_name = self._class_name_for_data_type(data_type.super_type)
        else:
            super_type_class_name = None

        if super_type_class_name:
            self.emit_line('_field_names_ = %s._field_names_.union({' % super_type_class_name)
        else:
            self.emit_line('_field_names_ = {')
        with self.indent():
            for field in data_type.fields:
                self.emit_line("'{}',".format(self.lang.format_variable(field.name)))
        if super_type_class_name:
            self.emit_line('})')
        else:
            self.emit_line('}')
        self.emit_empty_line()

        if super_type_class_name:
            self.emit_line('_fields_ = {}._fields_ + ['.format(super_type_class_name))
        else:
            self.emit_line('_fields_ = [')
        with self.indent():
            for field in data_type.fields:
                var_name = self.lang.format_variable(field.name)
                validator_name = '__{0}_data_type'.format(var_name)
                self.emit_line("('{}', {}, {}),".format(var_name, field.optional, validator_name))
        self.emit_line(']')
        self.emit_empty_line()

    def _generate_union_class_fields_for_reflection(self, data_type):

        assert not data_type.super_type, 'Unsupported: Inheritance of unions'

        self.emit_line('_field_names_ = {')
        with self.indent():
            for field in data_type.fields:
                self.emit_line("'{}',".format(self.lang.format_variable(field.name)))
        self.emit_line('}')
        self.emit_empty_line()

        self.emit_line('_fields_ = {')
        with self.indent():
            for field in data_type.fields:
                var_name = self.lang.format_variable(field.name)
                if is_symbol_type(field.data_type) or is_any_type(field.data_type):
                    self.emit_line("'{}': None,".format(var_name))
                else:
                    if not is_composite_type(field.data_type):
                        validator_name = '__{0}_data_type'.format(var_name)
                    else:
                        validator_name = self._class_name_for_data_type(field.data_type)
                    self.emit_line("'{}': {},".format(var_name, validator_name))
        self.emit_line('}')
        self.emit_empty_line()

    def _generate_struct_class_init(self, data_type):
        """Generates constructor for struct."""
        self.emit_line('def __init__(self):')
        with self.indent():
            lineno = self.lineno

            # Call the parent constructor if a super type exists
            if data_type.super_type:
                class_name = self._class_name_for_data_type(data_type)
                self.emit_line('super({}, self).__init__()'.format(class_name))

            for field in data_type.fields:
                field_var_name = self.lang.format_variable(field.name)
                self.emit_line('self._{} = None'.format(field_var_name))
                self.emit_line('self.__has_{} = False'.format(field_var_name))

            if lineno == self.lineno:
                self.emit_line('pass')
            self.emit_empty_line()

    def _python_type_mapping(self, data_type):
        """Map Babel data types to their most natural equivalent in Python
        for documentation purposes."""
        if is_string_type(data_type):
            return 'str'
        elif is_binary_type(data_type):
            return 'str'
        elif is_boolean_type(data_type):
            return 'bool'
        elif is_integer_type(data_type):
            return 'long'
        elif is_null_type(data_type):
            return 'None'
        elif is_timestamp_type(data_type):
            return 'datetime.datetime'
        elif is_composite_type(data_type):
            return self._class_name_for_data_type(data_type)
        elif is_list_type(data_type):
            return 'list of [{}]'.format(self._python_type_mapping(data_type.data_type))
        else:
            raise TypeError('Unknown data type %r' % data_type)

    def _generate_struct_class_properties(self, data_type):
        for field in data_type.fields:
            field_name = self.lang.format_method(field.name)

            # generate getter for field
            self.emit_line('@property')
            self.emit_line('def {}(self):'.format(field_name))
            with self.indent():
                self.emit_line('"""')
                if field.doc:
                    self.emit_wrapped_lines(self.docf(field.doc))
                self.emit_line(':rtype: {}'.format(self._python_type_mapping(field.data_type)))
                self.emit_line('"""')
                self.emit_line('if self.__has_{}:'.format(field_name))
                with self.indent():
                    self.emit_line('return self._{}'.format(field_name))

                self.emit_line('else:')
                with self.indent():
                    if field.optional:
                        if field.has_default:
                            self.emit_line(self.lang.format_obj(field.default))
                        else:
                            self.emit_line('return None')
                    else:
                        self.emit_line('raise KeyError("missing required field {!r}")'.format(field_name))
            self.emit_empty_line()

            # generate setter for field
            self.emit_line('@{}.setter'.format(field_name))
            self.emit_line('def {}(self, val):'.format(field_name))
            with self.indent():
                if field.optional:
                    self.emit_line('if val is None:')
                    with self.indent():
                        self.emit_line('del self.{}'.format(field_name))
                        self.emit_line('return')
                if is_composite_type(field.data_type):
                    self.emit_line('self.__{}_data_type.validate_type_only(val)'.format(field_name))
                else:
                    self.emit_line('self.__{}_data_type.validate(val)'.format(field_name))
                self.emit_line('self._{} = val'.format(field_name))
                self.emit_line('self.__has_{} = True'.format(field_name))
            self.emit_empty_line()

            # generate deleter for field
            self.emit_line('@{}.deleter'.format(field_name))
            self.emit_line('def {}(self):'.format(field_name))
            with self.indent():
                self.emit_line('self._{} = None'.format(field_name))
                self.emit_line('self.__has_{} = False'.format(field_name))
            self.emit_empty_line()

    def _generate_struct_class_repr(self, data_type):
        """The special __repr__() function will return a string of the class
        name, and if the class has fields, the first field as well."""
        self.emit_line('def __repr__(self):')
        with self.indent():
            if data_type.all_fields:
                self.emit_line("return '{0}({1}=%r)' % self._{1}".format(
                    self._class_name_for_data_type(data_type),
                    data_type.all_fields[0].name,
                ))
            else:
                self.emit_line("return '{}()'".format(self._class_name_for_data_type(data_type)))
        self.emit_empty_line()

    def _class_name_for_data_type(self, data_type):
        return self.lang.format_class(data_type.name)

    def _class_declaration_for_data_type(self, data_type):
        if data_type.super_type:
            extends = self._class_name_for_data_type(data_type.super_type)
        else:
            extends = 'object'
        return 'class {}({}):'.format(self._class_name_for_data_type(data_type), extends)

    def _is_instance_type(self, data_type):
        """The Python types to use in a call to isinstance() for the specified
        Babel data_type."""
        if isinstance(data_type, (UInt32, UInt64, Int32, Int64)):
            return 'numbers.Integral'
        elif isinstance(data_type, String):
            return 'six.string_types'
        elif is_timestamp_type(data_type):
            return 'datetime.datetime'
        else:
            return self.lang.format_type(data_type)

    #
    # Tagged Union Types
    #

    def _generate_union_class(self, data_type):
        """Defines a Python class that represents a union in Babel."""
        self.emit_line(self._class_declaration_for_data_type(data_type))
        with self.indent():
            if data_type.doc:
                self.emit_line('"""')
                self.emit_wrapped_lines(self.docf(data_type.doc))
                self.emit_empty_line()
                for field in data_type.fields:
                    if is_symbol_type(field.data_type):
                        ivar_doc = ':ivar {}: {}'.format(self.lang.format_class(field.name),
                                                         self.docf(field.doc))
                    elif is_composite_type(field.data_type):
                        ivar_doc = ':ivar {}: {}'.format(
                            self.lang.format_class(field.name),
                            self.docf(field.doc),
                        )
                    self.emit_wrapped_indented_lines(ivar_doc)
                self.emit_line('"""')
            self.emit_empty_line()

            self._generate_union_class_fields_for_reflection(data_type)
            self._generate_union_class_init(data_type)
            self._generate_union_class_symbol_creators(data_type)
            self._generate_union_class_is_set(data_type)
            self._generate_union_class_properties(data_type)
            self._generate_union_class_repr(data_type)

    def _generate_union_class_init(self, data_type):
        """Generates the __init__ method for the class."""
        self.emit_line('def __init__(self):')
        with self.indent():
            # Call the parent constructor if a super type exists
            if data_type.super_type:
                class_name = self._class_name_for_data_type(data_type)
                self.emit_line('super({}, self).__init__()'.format(class_name))

            for field in data_type.fields:
                field_var_name = self.lang.format_variable(field.name)
                if not is_symbol_type(field.data_type):
                    self.emit_line('self._{} = None'.format(field_var_name))
            self.emit_line('self._tag = None')
            self.emit_empty_line()

    def _generate_union_class_symbol_creators(self, data_type):
        class_name = self.lang.format_class(data_type.name)
        for field in data_type.fields:
            if is_symbol_type(field.data_type) or is_any_type(field.data_type):
                field_name = self.lang.format_method(field.name)
                self.emit_line('@classmethod')
                self.emit_line('def create_and_set_{}(cls):'.format(field_name))
                with self.indent():
                    self.emit_line('"""')
                    self.emit_wrapped_indented_lines(
                        ':rtype: {}'.format(class_name)
                    )
                    self.emit_line('"""')
                    self.emit_line('c = cls()')
                    self.emit_line('c.set_{}()'.format(field_name))
                    self.emit_line('return c')
                self.emit_empty_line()

    def _generate_union_class_is_set(self, data_type):
        for field in data_type.fields:
            field_name = self.lang.format_method(field.name)
            self.emit_line('def is_{}(self):'.format(field_name))
            with self.indent():
                self.emit_line('return self._tag == {!r}'.format(field_name))
            self.emit_empty_line()

    def _generate_union_class_properties(self, data_type):
        for field in data_type.fields:
            field_name = self.lang.format_method(field.name)

            if is_symbol_type(field.data_type) or is_any_type(field.data_type):
                self.emit_line('def set_{}(self):'.format(field_name))
                with self.indent():
                    self.emit_line('self._tag = {!r}'.format(field_name))
                self.emit_empty_line()
                continue

            # generate getter for field
            self.emit_line('@property')
            self.emit_line('def {}(self):'.format(field_name))
            with self.indent():
                self.emit_line('if not self.is_{}():'.format(field_name))
                with self.indent():
                    self.emit_line('raise KeyError("tag {!r} not set")'.format(field_name))
                if is_symbol_type(field.data_type):
                    self.emit_line('return {!r}'.format(field_name))
                else:
                    self.emit_line('return self._{}'.format(field_name))
            self.emit_empty_line()

            # generate setter for field
            self.emit_line('@{}.setter'.format(field_name))
            self.emit_line('def {}(self, val):'.format(field_name))
            with self.indent():
                if is_composite_type(field.data_type):
                    self.emit_line('self.__{}_data_type.validate_type_only(val)'.format(field_name))
                else:
                    self.emit_line('self.__{}_data_type.validate(val)'.format(field_name))
                self.emit_line('self._{} = val'.format(field_name))
                self.emit_line('self._tag = {!r}'.format(field_name))
            self.emit_empty_line()

    def _generate_union_class_repr(self, data_type):
        # The special __repr__() function will return a string of the class
        # name, and the selected tag
        self.emit_line('def __repr__(self):')
        with self.indent():
            if data_type.fields:
                self.emit_line("return '{}(%r)' % self._tag".format(
                    self._class_name_for_data_type(data_type),
                ))
            else:
                self.emit_line("return '{}()'".format(self._class_name_for_data_type(data_type)))
        self.emit_empty_line()

    #
    # Routes
    #
    def _generate_route_class(self, namespace, route):
        self.emit_line('class {}Route(object):'.format(self.lang.format_class(route.name)))
        with self.indent():
            if route.doc:
                self.emit_line('"""')
                self.emit_wrapped_lines(self.docf(route.doc))
                self.emit_line('"""')
            if route.request_data_type:
                self.emit_line('request_data_type = {}'.format(
                    self._determine_validator_type(route.request_data_type)))
            if route.response_data_type:
                self.emit_line('response_data_type = {}'.format(
                    self._determine_validator_type(route.response_data_type)))
            if route.error_data_type:
                self.emit_line('error_data_type = {}'.format(
                    self._determine_validator_type(route.error_data_type)))

            self.emit_empty_line()
            if route.attrs:
                self.emit_line('attrs = {')
                with self.indent():
                    for k, v in route.attrs.items():
                        self.emit_line("'{}': {},".format(k, self.lang.format_obj(v)))
                self.emit_line('}')
            else:
                self.emit_line('attrs = {}')
            self.emit_empty_line()