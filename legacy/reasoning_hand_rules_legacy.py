"""Hand-written conclusion rules from reasoning_understanding.py (moved Nov 6, 2026).

Replaced by reasoning_engine.py: general forms of reasoning that work on
anything she knows (Matthew: reasoning should reason, not have a rule per
topic). Kept for the record; nothing uses it.
"""


class _Old:
    # ---- what follows ----------------------------------------------------------
    def conclude(self, facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """New facts that follow from facts she has, with how sure and why."""
        out: List[Dict[str, Any]] = []
        known = {(str(f.get("subject")).casefold(), str(f.get("predicate")), str(f.get("object")).casefold())
                 for f in facts}

        def add(subject: str, predicate: str, obj: str, sure: float, why: str) -> None:
            key = (subject.casefold(), predicate, obj.casefold())
            if key in known or any((c["subject"].casefold(), c["predicate"], c["object"].casefold()) == key for c in out):
                return
            out.append({"subject": subject, "predicate": predicate, "object": obj, "sure": sure, "because": why})

        for f in facts:
            subject, predicate = str(f.get("subject") or ""), str(f.get("predicate") or "")
            obj = str(f.get("object") or "")
            if f.get("is_contradicted"):
                continue
            # "My dog is named Rex" is filed as (user, dog, Rex): Rex is a dog.
            base = fact_sure(f)  # a conclusion is no surer than what it rests on
            if subject == "user" and obj[:1].isupper() and predicate.isalpha() \
                    and predicate not in ("is", "is_a", "name") and kind_of(predicate):
                add(obj, "is_a", predicate, round(base * 0.98, 2), f"he said his {predicate} is {obj}")
                kind = kind_of(predicate)
                if kind and kind != "person":
                    add(obj, "is_a", kind, round(base * 0.95, 2), f"{obj} is his {predicate}, and a {predicate} is an {kind}"
                        if kind[:1] in "aeiou" else f"{obj} is his {predicate}, and a {predicate} is a {kind}")
            # "Rex is a dog": a dog is an animal, so Rex is an animal.
            if predicate == "is_a" and obj and not obj[:1].isupper():
                kind = kind_of(obj.split()[-1])
                if kind and kind != obj.casefold():
                    add(subject, "is_a", kind, round(base * 0.95, 2),
                        f"{subject} is a {obj}, and the dictionary puts a {obj} with {kind}s")
        return out

    def family(self, user_id: str, new: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """What follows about his family, from who is whose: two of his
        siblings are each other's siblings; his parent is his siblings' parent
        too. Each as sure as what it rests on, a little less."""
        body = self.ask("notus", "query_facts", {"query": "user", "user_id": user_id, "limit": 50}) or {}
        known = [f for f in body.get("facts") or [] if isinstance(f, dict)]
        if new:
            known.append(new)
        relatives = [(str(f.get("subject")), str(f.get("predicate")), str(f.get("object")), fact_sure(f))
                     for f in known if str(f.get("object") or "")[:1].isupper()
                     and str(f.get("predicate") or "").isalpha() and kind_of(str(f.get("predicate"))) == "person"]
        out: List[Dict[str, Any]] = []
        for owner in {r[0] for r in relatives}:
            siblings = [r for r in relatives if r[0] == owner and family_kind(r[1]) == "sibling"]
            parents = [r for r in relatives if r[0] == owner and family_kind(r[1]) == "parent"]
            whose = "his" if owner == "user" else f"{owner}'s"
            for a in siblings:
                for b in siblings:
                    if a[2] != b[2]:
                        out.append({"subject": b[2], "predicate": a[1], "object": a[2],
                                    "sure": round(min(a[3], b[3]) * 0.95, 2),
                                    "because": f"{a[2]} and {b[2]} are both {whose} siblings"})
                for parent in parents:
                    out.append({"subject": a[2], "predicate": parent[1], "object": parent[2],
                                "sure": round(min(a[3], parent[3]) * 0.9, 2),
                                "because": f"{parent[2]} is {whose} {parent[1]} and {a[2]} is {whose} {a[1]}"})
        return out

