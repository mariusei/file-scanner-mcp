"""A family of sibling extractors. Every one reads a node, then records it —
except the one planted outlier, which reads but never records. That broken
site is the divergence the detector should surface."""

from helpers import read_node, record, validate, normalize


def extract_table(n):
    node = read_node(n)
    validate(node)
    record(node)
    return node


def extract_view(n):
    node = read_node(n)
    record(node)
    return node


def extract_index(n):
    node = read_node(n)
    normalize(node)
    record(node)
    return node


def extract_function(n):
    node = read_node(n)
    validate(node)
    record(node)
    return node


def extract_procedure(n):
    node = read_node(n)
    record(node)
    return node


def extract_trigger(n):
    node = read_node(n)
    normalize(node)
    record(node)
    return node


def extract_sequence(n):
    node = read_node(n)
    record(node)
    return node


def extract_schema(n):
    node = read_node(n)
    validate(node)
    record(node)
    return node


def extract_legacy(n):
    # OUTLIER: reads the node like its siblings, but never records it.
    node = read_node(n)
    validate(node)
    return node
