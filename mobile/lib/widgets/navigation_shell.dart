import 'package:flutter/material.dart';

/// Four-tab application shell: 对话 / 工作台 / 空间 / 我的.
class NavigationShell extends StatefulWidget {
  const NavigationShell({
    super.key,
    required this.pages,
    this.initialIndex = 1,
    this.onTabChanged,
  });

  final List<Widget> pages;
  final int initialIndex;
  final ValueChanged<int>? onTabChanged;

  @override
  State<NavigationShell> createState() => _NavigationShellState();
}

class _NavigationShellState extends State<NavigationShell> {
  late int _index;

  static const _destinations = [
    NavigationDestination(
      icon: Icon(Icons.chat_bubble_outline_rounded),
      selectedIcon: Icon(Icons.chat_bubble_rounded),
      label: '对话',
    ),
    NavigationDestination(
      icon: Icon(Icons.grid_view_outlined),
      selectedIcon: Icon(Icons.grid_view_rounded),
      label: '工作台',
    ),
    NavigationDestination(
      icon: Icon(Icons.widgets_outlined),
      selectedIcon: Icon(Icons.widgets_rounded),
      label: '空间',
    ),
    NavigationDestination(
      icon: Icon(Icons.person_outline_rounded),
      selectedIcon: Icon(Icons.person_rounded),
      label: '我的',
    ),
  ];

  @override
  void initState() {
    super.initState();
    _index = widget.initialIndex.clamp(0, _destinations.length - 1);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: _index, children: widget.pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (value) {
          setState(() => _index = value);
          widget.onTabChanged?.call(value);
        },
        destinations: _destinations,
      ),
    );
  }
}
