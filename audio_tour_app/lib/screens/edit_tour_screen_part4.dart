part of 'edit_tour_screen.dart';

@override
Widget build(BuildContext context) {
  return Scaffold(
    appBar: AppBar(
      title: Text('Edit: ${widget.tourData['title']}'),
      backgroundColor: const Color(0xFF2c3e50),
      foregroundColor: Colors.white,
    ),
    body: _isLoading
       ? const Center(child: CircularProgressIndicator())
        : _stops.isEmpty
           ? const Center(
                child: Text(
                  'No stops found in this tour',
                  style: TextStyle(fontSize: 18, color: Colors.grey),
                ),
              )
            : Column(
                children: [
                  Container(
                    padding: const EdgeInsets.all(16),
                    color: Colors.blue.shade50,
                    child: Column(
                      children: [
                        Row(
                          children: [
                            Icon(Icons.info, color: Colors.blue.shade700),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                'Individual stops save automatically. Orange stops are modified.',
                                style: TextStyle(
                                  color: Colors.blue.shade800,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ),
                          ],
                        ),
                        if (_hasAnyChanges())...[
                          const SizedBox(height: 8),
                          Row(
                            children: [
                              Icon(Icons.warning, color: Colors.orange.shade700, size: 16),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(
                                  'You have unsaved changes. Tap Save All to push to backend.',
                                  style: TextStyle(
                                    color: Colors.orange.shade800,
                                    fontSize: 12,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ],
                      ],
                    ),
                  ),
                  Expanded(
                    child: ReorderableListView.builder(
                      itemCount: _stops.length,
                      onReorder: _reorderStops,
                      itemBuilder: (context, index) {
                        final stop = _stops[index];
                        return Card(
                          key: ValueKey(stop['stop_number']),
                          margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                          child: ListTile(
                            leading: CircleAvatar(
                              backgroundColor: stop['action'] == 'delete'
                                 ? Colors.red
                                  : stop['modified'] == true
                                     ? Colors.orange
                                      : Colors.blue,
                              child: Text('${stop['stop_number']}'),
                            ),
                            title: Text(
                              stop['title'],
                              style: TextStyle(
                                decoration: stop['action'] == 'delete'
                                   ? TextDecoration.lineThrough
                                    : null,
                              ),
                            ),
                            subtitle: Text(
                              stop['text'],
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                            ),
                            trailing: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                if (stop['action'] == 'add')...[
                                  const Icon(Icons.add_circle, color: Colors.green, size: 16),
                                  const SizedBox(width: 4),
                                  const Text('New', style: TextStyle(color: Colors.green, fontSize: 12)),
                                  const SizedBox(width: 8),
                                ],
                                if (stop['action'] == 'delete')...[
                                  const Icon(Icons.delete, color: Colors.red, size: 16),
                                  const SizedBox(width: 4),
                                  const Text('Delete', style: TextStyle(color: Colors.red, fontSize: 12)),
                                  const SizedBox(width: 8),
                                ],
                                if (stop['moved'] == true)...[
                                  const Icon(Icons.swap_vert, color: Colors.purple, size: 16),
                                  const SizedBox(width: 4),
                                  const Text('Moved', style: TextStyle(color: Colors.purple, fontSize: 12)),
                                  const SizedBox(width: 8),
                                ],
                                if (stop['modified'] == true &&
                                    stop['action']!= 'add' &&
                                    stop['action']!= 'delete')...[
                                  const Icon(Icons.circle, color: Colors.orange, size: 12),
                                  const SizedBox(width: 4),
                                  const Text('Modified', style: TextStyle(color: Colors.orange, fontSize: 12)),
                                  const SizedBox(width: 8),
                                ],
                                if (stop['action']!= 'delete')
                                  Icon(Icons.edit, color: Colors.grey[600]),
                                const SizedBox(width: 8),
                                Icon(Icons.drag_handle, color: Colors.grey[400]),
                              ],
                            ),
                            onTap: stop['action'] == 'delete'? null : () => _editStop(stop),
                          ),
                        );
                      },
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    child: OutlinedButton.icon(
                      onPressed: _addNewStop,
                      icon: const Icon(Icons.add, color: Colors.green),
                      label: const Text('Add Stop', style: TextStyle(color: Colors.green)),
                      style: OutlinedButton.styleFrom(
                        side: const BorderSide(color: Colors.green),
                      ),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      children: [
                        Expanded(
                          child: OutlinedButton(
                            onPressed: () => Navigator.pop(context),
                            child: const Text('Cancel'),
                          ),
                        ),
                        const SizedBox(width: 16),
                        Expanded(
                          child: ElevatedButton(
                            onPressed: _hasAnyChanges()? _saveAllChanges : null,
                            style: ElevatedButton.styleFrom(
                              backgroundColor: const Color(0xFF2c3e50),
                              foregroundColor: Colors.white,
                            ),
                            child: const Text('Save All'),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
  );
}