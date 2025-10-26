  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Edit: ${widget.tourData['title']}'),
        backgroundColor: Color(0xFF2c3e50),
        foregroundColor: Colors.white,
      ),
      body: _isLoading
          ? Center(child: CircularProgressIndicator())
          : _stops.isEmpty
              ? Center(
                  child: Text(
                    'No stops found in this tour',
                    style: TextStyle(fontSize: 18, color: Colors.grey),
                  ),
                )
              : Column(
                  children: [
                    Container(
                      padding: EdgeInsets.all(16),
                      color: Colors.blue.shade50,
                      child: Column(
                        children: [
                          Row(
                            children: [
                              Icon(Icons.info, color: Colors.blue.shade700),
                              SizedBox(width: 8),
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
                          if (_hasAnyChanges()) ...[
                            SizedBox(height: 8),
                            Row(
                              children: [
                                Icon(Icons.warning, color: Colors.orange.shade700, size: 16),
                                SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    'You have unsaved changes. Use "Save All Changes" for bulk save.',
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
                            margin: EdgeInsets.all(8),
                            child: ListTile(
                              leading: CircleAvatar(
                                backgroundColor: stop['modified'] == true 
                                    ? Colors.orange 
                                    : stop['action'] == 'delete' 
                                        ? Colors.red
                                        : stop['action'] == 'add'
                                            ? Colors.green
                                            : Color(0xFF3498db),
                                child: Text(
                                  '${stop['stop_number']}',
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
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
                                stop['text'].length > 100
                                    ? '${stop['text'].substring(0, 100)}...'
                                    : stop['text'],
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  decoration: stop['action'] == 'delete' 
                                      ? TextDecoration.lineThrough 
                                      : null,
                                ),
                              ),
                              trailing: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  if (stop['action'] == 'add') ...[
                                    Icon(Icons.add_circle, color: Colors.green, size: 16),
                                    SizedBox(width: 4),
                                    Text('New', style: TextStyle(color: Colors.green, fontSize: 12)),
                                    SizedBox(width: 8),
                                  ],
                                  if (stop['action'] == 'delete') ...[
                                    Icon(Icons.delete, color: Colors.red, size: 16),
                                    SizedBox(width: 4),
                                    Text('Delete', style: TextStyle(color: Colors.red, fontSize: 12)),
                                    SizedBox(width: 8),
                                  ],
                                  if (stop['moved'] == true) ...[
                                    Icon(Icons.swap_vert, color: Colors.purple, size: 16),
                                    SizedBox(width: 4),
                                    Text('Moved', style: TextStyle(color: Colors.purple, fontSize: 12)),
                                    SizedBox(width: 8),
                                  ],
                                  if (stop['modified'] == true && stop['action'] != 'add' && stop['action'] != 'delete') ...[
                                    Icon(Icons.circle, color: Colors.orange, size: 12),
                                    SizedBox(width: 4),
                                    Text('Modified', style: TextStyle(color: Colors.orange, fontSize: 12)),
                                    SizedBox(width: 8),
                                  ],
                                  if (stop['action'] != 'delete') 
                                    Icon(Icons.edit, color: Colors.grey[600]),
                                  SizedBox(width: 8),
                                  Icon(Icons.drag_handle, color: Colors.grey[400]),
                                ],
                              ),
                              onTap: stop['action'] == 'delete' ? null : () => _editStop(stop),
                            ),
                          );
                        },
                      ),
                    ),
                    Container(
                      padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                      child: OutlinedButton.icon(
                        onPressed: _addNewStop,
                        icon: Icon(Icons.add, color: Colors.green),
                        label: Text('Add Stop', style: TextStyle(color: Colors.green)),
                        style: OutlinedButton.styleFrom(
                          side: BorderSide(color: Colors.green),
                        ),
                      ),
                    ),
                    Container(
                      padding: EdgeInsets.all(16),
                      child: Row(
                        children: [
                          Expanded(
                            child: OutlinedButton(
                              onPressed: () => Navigator.pop(context),
                              child: Text('Cancel'),
                            ),
                          ),
                          SizedBox(width: 16),
                          Expanded(
                            child: ElevatedButton(
                              onPressed: _hasAnyChanges() ? () async => await _saveAllChanges() : null,
                              child: Text(_hasAnyChanges() 
                                  ? 'Save All Changes (${_getModifiedCount()})' 
                                  : 'No Changes'),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
    );
  }
}