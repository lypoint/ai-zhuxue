import 'dart:convert';
import 'dart:io';
import 'package:path_provider/path_provider.dart';

/// One private, account-scoped draft; logout invalidates queued writes too.
class StudentDrafts {
  static Future<void> _pending = Future.value();
  static int _generation = 0;
  static bool _used = false;
  final String owner;
  final int _createdGeneration = _generation;
  StudentDrafts(this.owner) {
    _used = true;
  }

  static Future<File> _file() async {
    _used = true;
    return File(
      '${(await getApplicationSupportDirectory()).path}/student-draft.json',
    );
  }

  static Future<T> _serial<T>(Future<T> Function() action) {
    final result = _pending.then((_) => action());
    _pending = result.then<void>((_) {}, onError: (Object _) {});
    return result;
  }

  Future<Map<String, dynamic>?> load() => _serial(() async {
    if (_createdGeneration != _generation) return null;
    final file = await _file();
    if (!await file.exists()) return null;
    try {
      final data =
          jsonDecode(await file.readAsString()) as Map<String, dynamic>;
      if (data['text'] is! String ||
          data['images'] is! List ||
          (data['conversation_id'] != null &&
              data['conversation_id'] is! int) ||
          (data['images'] as List).length > 3) {
        throw const FormatException('Invalid draft');
      }
      for (final image in data['images'] as List) {
        if (image is! String) throw const FormatException('Invalid image');
        base64Decode(image);
      }
      final saved = DateTime.parse(data['saved_at'] as String);
      if (data['owner'] != owner ||
          DateTime.now().difference(saved) > const Duration(days: 7)) {
        await file.delete();
        return null;
      }
      return data;
    } on FormatException {
      await file.delete();
      return null;
    } on TypeError {
      await file.delete();
      return null;
    }
  });

  Future<void> save(Map<String, dynamic> draft) => _serial(() async {
    if (_createdGeneration != _generation) return;
    final file = await _file();
    if ((draft['text'] as String).isEmpty &&
        (draft['images'] as List).isEmpty) {
      if (await file.exists()) await file.delete();
      return;
    }
    await file.parent.create(recursive: true);
    final temporary = File('${file.path}.tmp');
    await temporary.writeAsString(
      jsonEncode({
        ...draft,
        'owner': owner,
        'saved_at': DateTime.now().toUtc().toIso8601String(),
      }),
      flush: true,
    );
    await temporary.rename(file.path);
  });

  static Future<void> clear() {
    ++_generation;
    if (!_used) return Future.value();
    return _serial(() async {
      for (final file in [await _file(), File('${(await _file()).path}.tmp')]) {
        if (await file.exists()) await file.delete();
      }
    });
  }
}
