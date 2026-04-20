import ifcopenshell
import ifcopenshell.util.element


def get_properties_by_global_id(model: ifcopenshell.file, global_id: str) -> dict:
    try:
        ifc_object = model.by_id(global_id)

        if not ifc_object:
            return {"error": f"Object with GlobalId '{global_id}' not found in the model."}

    except Exception as e:
        return {"error": f"Failed to find object '{global_id}': {str(e)}"}

    gui_data = {
        "Properties": {},
        "Classification": [],
        "Relations": []
    }

    gui_data["Properties"]["Element Specific"] = {
        "Guid": str(ifc_object.GlobalId),
        "IfcEntity": str(ifc_object.is_a()),
        "Name": str(ifc_object.Name) if getattr(ifc_object, "Name", None) else "",
        "Description": str(ifc_object.Description) if getattr(ifc_object, "Description", None) else ""
    }

    psets = ifcopenshell.util.element.get_psets(ifc_object)

    if psets:
        for pset_name, properties in psets.items():
            properties.pop('id', None)
            if not properties:
                continue

            if pset_name.startswith("Qto_") or "Quantity" in pset_name:
                gui_data["Location"][pset_name] = properties
            else:
                gui_data["Properties"][pset_name] = properties

    if hasattr(ifc_object, "HasAssociations"):
        for association in ifc_object.HasAssociations:
            if association.is_a("IfcRelAssociatesClassification"):
                rel = association.RelatingClassification

                class_data = {
                    "Name": str(rel.Name) if getattr(rel, "Name", None) else "N/A",
                    "Identification": str(rel.Identification) if getattr(rel, "Identification", None) else "N/A",
                    "Reference": str(rel.ItemReference) if getattr(rel, "ItemReference", None) else "N/A"
                }
                gui_data["Classification"].append(class_data)

    relations_list = []

    def add_relation(rel_type: str, related_element):
        name = str(related_element.Name) if getattr(related_element, "Name", None) else "Unnamed"
        relations_list.append({
            "Type": rel_type,
            "Name": f"{name} ({related_element.is_a()})"
        })

    if hasattr(ifc_object, "ContainedInStructure") and ifc_object.ContainedInStructure:
        for rel in ifc_object.ContainedInStructure:
            add_relation("Contained In", rel.RelatingStructure)

    if hasattr(ifc_object, "ContainsElements") and ifc_object.ContainsElements:
        for rel in ifc_object.ContainsElements:
            for child in rel.RelatedElements:
                add_relation("Contains", child)

    if hasattr(ifc_object, "Decomposes") and ifc_object.Decomposes:
        for rel in ifc_object.Decomposes:
            add_relation("Decomposes (Child of)", rel.RelatingObject)

    if hasattr(ifc_object, "IsDecomposedBy") and ifc_object.IsDecomposedBy:
        for rel in ifc_object.IsDecomposedBy:
            for child in rel.RelatedObjects:
                add_relation("Decomposed By (Parent of)", child)

    gui_data["Relations"] = relations_list

    return gui_data