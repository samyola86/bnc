/** Update only the editable preview; persisted revisions retain their original layout. */
export function editableNewspaper<T extends { template_id: string; template_version: 1 | 2; layout_version: 1 | 2 }>(value: T, editable: boolean): T {
  return editable && value.template_id === "newspaper" && value.template_version === 1
    ? { ...value, template_version: 2, layout_version: 2 }
    : value;
}
