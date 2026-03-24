import ifcopenshell

def get_project_hierarchy(model: ifcopenshell.file) -> list:

    def traverse_node(entity) -> dict:
        node_data = {
            "GlobalId": str(entity.GlobalId),
            "Name": str(entity.Name) if getattr(entity, "Name", None) else "Без имени",
            "Type": str(entity.is_a()),
            "Children": []
        }

        if hasattr(entity, "IsDecomposedBy") and entity.IsDecomposedBy:
            for rel in entity.IsDecomposedBy:
                if hasattr(rel, "RelatedObjects") and rel.RelatedObjects:
                    for child in rel.RelatedObjects:
                        node_data["Children"].append(traverse_node(child))

        if hasattr(entity, "ContainsElements") and entity.ContainsElements:
            for rel in entity.ContainsElements:
                if hasattr(rel, "RelatedElements") and rel.RelatedElements:
                    for child_element in rel.RelatedElements:
                        node_data["Children"].append(traverse_node(child_element))

        node_data["Children"] = sorted(node_data["Children"], key=lambda x: (x["Type"], x["Name"]))
        return node_data

    projects = model.by_type("IfcProject")

    clean_hierarchy = []
    for project in projects:
        clean_hierarchy.append(traverse_node(project))

    return clean_hierarchy