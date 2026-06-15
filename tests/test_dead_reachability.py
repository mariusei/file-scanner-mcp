"""Cross-language safety for dead-code detection.

The framework only claims a definition dead if its LANGUAGE has opted in
(CLAIMS_DEAD) and adjudges it off-graph-unreachable. A language whose reachability
is not modelled is silent — never a false "this is dead". These tests lock that:
public/exported API is never flagged, and un-opted-in languages stay silent.
"""
import tempfile
from pathlib import Path

from scantool.code_map import CodeMap, clear_corpus_cache
from scantool.connectivity import _compute_dead


def _dead_names(filename: str, source: str):
    d = tempfile.mkdtemp()
    Path(d, filename).write_text(source)
    clear_corpus_cache()
    result = CodeMap(d).analyze()
    dead, _dyn = _compute_dead(d, result)
    return {qual.split(".")[-1] for _f, qual in dead}


def test_go_exports_by_capitalisation():
    dead = _dead_names(
        "a.go",
        "package main\n"
        "func Exported() int { return 1 }\n"        # capitalised -> public -> reachable
        "func unexportedDead() int { return 2 }\n"  # lower-case, unused -> dead
        "func main() { _ = caller() }\nfunc caller() int { return 0 }\n",
    )
    assert "Exported" not in dead
    assert "unexportedDead" in dead


def test_java_public_is_reachable():
    dead = _dead_names(
        "A.java",
        "class A {\n"
        "  public int exported() { return 1; }\n"   # public -> reachable
        "  private int privateDead() { return 2; }\n"  # private, unused -> dead
        "}\n",
    )
    assert "exported" not in dead
    assert "privateDead" in dead


def test_rust_pub_and_traits_reachable():
    # Rust opted in: `pub` is public API; trait methods (declaration or default
    # body) and trait-impl methods are reached off-graph via dispatch -> never
    # flagged. Only zero-inbound private free fns / inherent-impl methods are dead.
    dead = _dead_names(
        "a.rs",
        "pub fn exported_api() -> i32 { 1 }\n"           # pub -> reachable
        "fn private_unused() -> i32 { 2 }\n"             # private free fn, unused -> dead
        "pub trait Service {\n"
        "    fn default_hook(&self) -> i32 { 42 }\n"     # pub-trait default body -> reachable
        "}\n"
        "struct Impl1;\n"
        "impl Service for Impl1 { fn hook_impl(&self) -> i32 { 1 } }\n"  # trait-impl -> reachable
        "struct Internal;\n"
        "impl Internal { fn helper_unused(&self) -> i32 { 9 } }\n"  # inherent, unused -> dead
        "fn main() {}\n",
    )
    assert "exported_api" not in dead       # public API never flagged
    assert "default_hook" not in dead       # public trait member never flagged
    assert "hook_impl" not in dead          # trait-impl method never flagged
    assert "private_unused" in dead         # genuinely dead private free fn
    assert "helper_unused" in dead          # genuinely dead inherent-impl method


def test_php_private_only():
    # PHP opted in: no-modifier defaults to public; public/protected are external/
    # subclass API and magic/interface methods are runtime/contract — all reachable.
    # Only a zero-inbound `private` method is a genuine dead candidate.
    dead = _dead_names(
        "a.php",
        "<?php\n"
        "interface Repo { public function find(); }\n"
        "class Service implements Repo {\n"
        "  public function find() { return 1; }\n"          # public -> reachable
        "  protected function forSubclass() { return 2; }\n"  # protected (subclass API) -> reachable
        "  private function privateDead() { return 3; }\n"  # private, unused -> dead
        "  private function privateUsed() { return 4; }\n"
        "  public function caller() { return $this->privateUsed(); }\n"
        "  public function __get($k) { return null; }\n"    # magic -> reachable
        "}\n",
    )
    assert "find" not in dead          # public API never flagged
    assert "forSubclass" not in dead   # protected (subclass API) never flagged
    assert "__get" not in dead         # magic method never flagged
    assert "privateDead" in dead       # genuinely dead private method


def test_zig_pub_reachable():
    # Zig opted in: `pub`/`export`/`extern` are public/external API; a non-pub
    # declaration is file-private, so a zero-inbound one is dead.
    dead = _dead_names(
        "a.zig",
        "pub fn publicApi() void {}\n"               # pub -> reachable
        "fn privateDead() void {}\n"                 # non-pub, unused -> dead
        "fn privateUsed() void {}\n"
        "pub fn caller() void { privateUsed(); }\n"
        "export fn c_abi() void {}\n",               # C ABI -> reachable
    )
    assert "publicApi" not in dead    # pub API never flagged
    assert "c_abi" not in dead        # exported C ABI never flagged
    assert "privateDead" in dead      # non-pub, unused -> dead


def test_swift_protocol_witnesses_protected():
    # Swift opted in with corpus-level protocol-conformance resolution: a witness to
    # a conformed protocol (corpus-defined or known stdlib) is reachable via
    # dispatch; a type conforming to an UNKNOWN external protocol is protected
    # wholesale (cannot tell witness from helper); only genuine internal helpers in
    # fully-accountable types — and private/public per the per-def rule — are judged.
    dead = _dead_names(
        "a.swift",
        "protocol Drawable { func draw() }\n"
        "struct Shape: Drawable {\n"
        "  func draw() {}\n"                       # corpus-protocol witness -> reachable
        "  func internalHelperDead() {}\n"         # internal helper, accountable type -> dead
        "}\n"
        "struct Money: Codable {\n"
        "  func encode(to e: Encoder) {}\n"        # stdlib Codable witness -> reachable
        "}\n"
        "class VC: UITableViewDataSource {\n"      # unknown external -> whole type protected
        "  func numberOfRows() -> Int { 0 }\n"
        "}\n"
        "public func publicApi() {}\n"             # public -> reachable
        "private func privateDead() {}\n",         # private, unused -> dead
    )
    assert "draw" not in dead             # protocol witness protected
    assert "encode" not in dead           # stdlib (Codable) witness protected
    assert "numberOfRows" not in dead     # unknown-external conformer protected wholesale
    assert "publicApi" not in dead        # public API never flagged
    assert "internalHelperDead" in dead   # internal helper in accountable type -> dead
    assert "privateDead" in dead          # private, unused -> dead


def test_cpp_internal_linkage_only():
    # C/C++ opted in: external-linkage free functions are reachable (callable from
    # another translation unit); only `static` (file-local) free functions and
    # private members are flaggable. public/virtual members stay reachable.
    dead = _dead_names(
        "a.cpp",
        "static int fileLocalDead() { return 1; }\n"     # static, unused -> dead
        "int externalApi() { return 2; }\n"              # external linkage -> reachable
        "class Widget {\n"
        "public:\n"
        "  void publicApi() {}\n"                         # public -> reachable
        "  virtual void onDraw() {}\n"                    # virtual -> reachable
        "private:\n"
        "  int privateDead() { return 3; }\n"            # private, unused -> dead
        "};\n",
    )
    assert "externalApi" not in dead     # external linkage never flagged (cross-TU)
    assert "publicApi" not in dead       # public API never flagged
    assert "onDraw" not in dead          # virtual (dispatched) never flagged
    assert "fileLocalDead" in dead       # static, unused -> genuinely dead
    assert "privateDead" in dead         # private, unused -> genuinely dead


def test_typescript_exports_and_jsx_reachable():
    # TS opted in: exports are public API; interface methods and non-private class
    # methods are reachable; a component used via `<Comp/>` gets a JSX reference
    # edge so it is never falsely dead. Only non-exported, never-referenced defs and
    # private members are flagged.
    dead = _dead_names(
        "App.tsx",
        "export function ExportedFn() { return 1; }\n"   # export -> reachable
        "function privateDeadFn() { return 2; }\n"       # not exported, unused -> dead
        "function UsedComp() { return <div/>; }\n"        # used via JSX -> reachable
        "function UnusedComp() { return <div/>; }\n"      # never referenced -> dead
        "function App() { return <UsedComp/>; }\n"
        "export const Root = () => <App/>;\n"
        "export class Service {\n"
        "  publicMethod() { return 1; }\n"               # public on exported class -> reachable
        "  private secret() { return 2; }\n"             # private, unused -> dead
        "}\n",
    )
    assert "ExportedFn" not in dead       # exported public API never flagged
    assert "UsedComp" not in dead         # JSX-referenced, not dead
    assert "publicMethod" not in dead     # public method never flagged
    assert "privateDeadFn" in dead        # genuinely dead non-exported fn
    assert "UnusedComp" in dead           # never-referenced component
    assert "secret" in dead               # genuinely dead private method


def test_csharp_public_and_interface_reachable():
    # C# opted in: public/internal/protected and interface members (implicitly
    # public) are reachable; a member with no modifier is implicitly private, so a
    # zero-inbound one is dead.
    dead = _dead_names(
        "A.cs",
        "public interface IRepo { int Find(); }\n"     # interface member -> reachable
        "public class A {\n"
        "  public int Exported() { return 1; }\n"      # public -> reachable
        "  private int PrivateUnused() { return 2; }\n"  # private, unused -> dead
        "  int ImplicitPrivateDead() { return 3; }\n"  # no modifier = private -> dead
        "}\n",
    )
    assert "Exported" not in dead       # public API never flagged
    assert "Find" not in dead           # interface member never flagged
    assert "PrivateUnused" in dead      # genuinely dead private method
    assert "ImplicitPrivateDead" in dead  # implicitly-private, unused -> dead
