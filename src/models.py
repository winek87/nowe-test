# src/models.py
import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import re
import logging

logger = logging.getLogger(__name__)

class MediaInfo:
    def __init__(self,
                 file_path: Path,
                 duration: Optional[float] = None,
                 video_codec: Optional[str] = None,
                 audio_codec: Optional[str] = None,
                 width: Optional[int] = None,
                 height: Optional[int] = None,
                 format_name: Optional[str] = None,
                 bit_rate: Optional[int] = None,
                 frame_rate: Optional[str] = None,
                 error_message: Optional[str] = None):
        self.file_path = file_path
        self.duration = duration
        self.video_codec = video_codec
        self.audio_codec = audio_codec
        self.width = width
        self.height = height
        self.format_name = format_name
        self.bit_rate = bit_rate
        self.frame_rate = frame_rate
        self.error_message = error_message

    def to_dict(self) -> Dict[str, Any]:
        return {
            'file_path': str(self.file_path), 'duration': self.duration,
            'video_codec': self.video_codec, 'audio_codec': self.audio_codec,
            'width': self.width, 'height': self.height,
            'format_name': self.format_name, 'bit_rate': self.bit_rate,
            'frame_rate': self.frame_rate, 'error_message': self.error_message
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MediaInfo':
        file_path_val = data.get('file_path')
        if isinstance(file_path_val, str): file_path = Path(file_path_val)
        elif isinstance(file_path_val, Path): file_path = file_path_val
        else:
            if file_path_val is None: raise ValueError(f"Brak 'file_path' w MediaInfo: {data}")
            raise ValueError(f"Nieprawidłowy typ dla 'file_path' w MediaInfo: {type(file_path_val)}")
        return cls(
            file_path=file_path, duration=data.get('duration'), video_codec=data.get('video_codec'),
            audio_codec=data.get('audio_codec'), width=data.get('width'), height=data.get('height'),
            format_name=data.get('format_name'), bit_rate=data.get('bit_rate'),
            frame_rate=data.get('frame_rate'), error_message=data.get('error_message')
        )

class EncodingProfile:
    def __init__(self, id: uuid.UUID, name: str, description: Optional[str], ffmpeg_params: List[str], output_extension: str, output_settings: Optional[Dict[str, Any]] = None):
        self.id = id; self.name = name; self.description = description if description else ""; self.ffmpeg_params = ffmpeg_params; self.output_extension = output_extension.lstrip('.'); self.output_settings = output_settings if output_settings is not None else {}
    def to_dict(self) -> Dict[str, Any]: return {'id': str(self.id), 'name': self.name, 'description': self.description, 'ffmpeg_params': self.ffmpeg_params, 'output_extension': self.output_extension, 'output_settings': self.output_settings}
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EncodingProfile':
        profile_id_val = data.get('id'); profile_id: uuid.UUID
        if isinstance(profile_id_val, uuid.UUID): profile_id = profile_id_val
        elif isinstance(profile_id_val, str):
            try: profile_id = uuid.UUID(profile_id_val)
            except ValueError: logger.warning(f"Nieprawidłowy format UUID '{profile_id_val}'. Generowanie nowego ID."); profile_id = uuid.uuid4()
        elif profile_id_val is None: profile_id = uuid.uuid4()
        else: raise ValueError(f"Nieprawidłowy typ dla ID profilu: {type(profile_id_val)}.")
        name = data.get('name'); description = data.get('description', ""); ffmpeg_params = data.get('ffmpeg_params'); output_extension = data.get('output_extension')
        if not all([name, ffmpeg_params is not None, output_extension]): raise ValueError("Słownik EncodingProfile nie zawiera wymaganych pól.")
        if not isinstance(ffmpeg_params, list): raise ValueError("ffmpeg_params musi być listą.")
        return cls(id=profile_id, name=name, description=description, ffmpeg_params=ffmpeg_params, output_extension=output_extension, output_settings=data.get('output_settings'))

class RepairProfile:
    """Definiuje profil naprawy FFmpeg."""
    def __init__(self,
                 id: uuid.UUID,
                 name: str,
                 description: Optional[str],
                 ffmpeg_params: List[str],
                 applies_to_mkv_only: bool = False,
                 copy_tags: bool = True
                ):
        self.id = id
        self.name = name
        self.description = description if description else ""
        self.ffmpeg_params = ffmpeg_params
        self.applies_to_mkv_only = applies_to_mkv_only
        self.copy_tags = copy_tags

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': str(self.id),
            'name': self.name,
            'description': self.description,
            'ffmpeg_params': self.ffmpeg_params,
            'applies_to_mkv_only': self.applies_to_mkv_only,
            'copy_tags': self.copy_tags
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RepairProfile':
        profile_id_val = data.get('id')
        profile_id: uuid.UUID
        if isinstance(profile_id_val, uuid.UUID): profile_id = profile_id_val
        elif isinstance(profile_id_val, str):
            try: profile_id = uuid.UUID(profile_id_val)
            except ValueError: logger.warning(f"Nieprawidłowy format UUID '{profile_id_val}' w RepairProfile. Generowanie nowego ID."); profile_id = uuid.uuid4()
        elif profile_id_val is None: profile_id = uuid.uuid4()
        else: raise ValueError(f"Nieprawidłowy typ dla ID profilu naprawy: {type(profile_id_val)}.")
        
        name = data.get('name')
        ffmpeg_params = data.get('ffmpeg_params')

        if not name or not isinstance(name, str):
            raise ValueError("Nazwa profilu naprawy (name) jest wymagana i musi być tekstem.")
        if not ffmpeg_params or not isinstance(ffmpeg_params, list):
            raise ValueError("Parametry FFmpeg (ffmpeg_params) są wymagane i muszą być listą.")

        return cls(
            id=profile_id,
            name=name,
            description=data.get('description', ""),
            ffmpeg_params=ffmpeg_params,
            applies_to_mkv_only=data.get('applies_to_mkv_only', False),
            copy_tags=data.get('copy_tags', True)
        )

class ProcessedFile:
    def __init__(self, file_id: uuid.UUID, original_path: Path, status: str, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None, duration_seconds: Optional[float] = None, output_path: Optional[Path] = None, error_message: Optional[str] = None, media_info: Optional[MediaInfo] = None):
        self.file_id = file_id; self.original_path = original_path; self.status = status; self.start_time = start_time; self.end_time = end_time; self.duration_seconds = duration_seconds; self.output_path = output_path; self.error_message = error_message; self.media_info = media_info
    def to_dict(self) -> Dict[str, Any]: return {'file_id': str(self.file_id), 'original_path': str(self.original_path), 'status': self.status, 'start_time': self.start_time.isoformat() if self.start_time else None, 'end_time': self.end_time.isoformat() if self.end_time else None, 'duration_seconds': self.duration_seconds, 'output_path': str(self.output_path) if self.output_path else None, 'error_message': self.error_message, 'media_info': self.media_info.to_dict() if self.media_info else None}
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProcessedFile':
        file_id_val = data['file_id']; file_id = file_id_val if isinstance(file_id_val, uuid.UUID) else uuid.UUID(str(file_id_val))
        original_path_val = data['original_path']; original_path = original_path_val if isinstance(original_path_val, Path) else Path(str(original_path_val))
        status = data['status']
        start_time_val = data.get('start_time'); start_time = datetime.fromisoformat(start_time_val) if isinstance(start_time_val, str) else start_time_val if isinstance(start_time_val, datetime) else None
        end_time_val = data.get('end_time'); end_time = datetime.fromisoformat(end_time_val) if isinstance(end_time_val, str) else end_time_val if isinstance(end_time_val, datetime) else None
        duration_seconds = data.get('duration_seconds')
        output_path_val = data.get('output_path'); output_path = Path(str(output_path_val)) if output_path_val and not isinstance(output_path_val, Path) else output_path_val if isinstance(output_path_val, Path) else None
        error_message = data.get('error_message')
        media_info_data = data.get('media_info'); media_info = MediaInfo.from_dict(media_info_data) if isinstance(media_info_data, dict) else media_info_data if isinstance(media_info_data, MediaInfo) else None
        return cls(file_id=file_id, original_path=original_path, status=status, start_time=start_time, end_time=end_time, duration_seconds=duration_seconds, output_path=output_path, error_message=error_message, media_info=media_info)

class JobState:
    def __init__(self, job_id: uuid.UUID, source_directory: Path, selected_profile_id: uuid.UUID, status: str, start_time: datetime, processed_files: List[ProcessedFile], total_files: int = 0, end_time: Optional[datetime] = None, error_message: Optional[str] = None):
        self.job_id = job_id; self.source_directory = source_directory; self.selected_profile_id = selected_profile_id; self.status = status; self.start_time = start_time; self.processed_files = processed_files if processed_files is not None else []; self.total_files = total_files; self.end_time = end_time; self.error_message = error_message
    def to_dict(self) -> Dict[str, Any]: return {'job_id': str(self.job_id), 'source_directory': str(self.source_directory), 'selected_profile_id': str(self.selected_profile_id), 'status': self.status, 'start_time': self.start_time.isoformat(), 'processed_files': [pf.to_dict() for pf in self.processed_files], 'total_files': self.total_files, 'end_time': self.end_time.isoformat() if self.end_time else None, 'error_message': self.error_message}
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'JobState':
        job_id_val = data.get('job_id');
        if not job_id_val: raise ValueError("Brak 'job_id' w danych JobState.")
        job_id = job_id_val if isinstance(job_id_val, uuid.UUID) else uuid.UUID(str(job_id_val))
        source_dir_val = data.get('source_directory');
        if not source_dir_val: raise ValueError("Brak 'source_directory' w danych JobState.")
        source_directory = Path(str(source_dir_val)) if not isinstance(source_dir_val, Path) else source_dir_val
        selected_profile_id_val = data.get('selected_profile_id');
        if not selected_profile_id_val: raise ValueError("Brak 'selected_profile_id' w danych JobState.")
        selected_profile_id = selected_profile_id_val if isinstance(selected_profile_id_val, uuid.UUID) else uuid.UUID(str(selected_profile_id_val))
        status = data.get('status');
        if not status: raise ValueError("Brak 'status' w danych JobState.")
        start_time_val = data.get('start_time');
        if not start_time_val: raise ValueError("Brak 'start_time' w danych JobState.")
        start_time = start_time_val if isinstance(start_time_val, datetime) else datetime.fromisoformat(start_time_val)
        processed_files_data = data.get('processed_files', [])
        processed_files = [ProcessedFile.from_dict(pf_data) if isinstance(pf_data, dict) else pf_data for pf_data in processed_files_data if isinstance(pf_data, (dict, ProcessedFile))]
        total_files = data.get('total_files', len(processed_files))
        end_time_val = data.get('end_time'); end_time = end_time_val if isinstance(end_time_val, datetime) else datetime.fromisoformat(end_time_val) if isinstance(end_time_val, str) else None
        error_message = data.get('error_message')
        return cls(job_id=job_id, source_directory=source_directory, selected_profile_id=selected_profile_id, status=status, start_time=start_time, processed_files=processed_files, total_files=total_files, end_time=end_time, error_message=error_message)

class AppJSONEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Path): return str(obj)
        if isinstance(obj, datetime): return obj.isoformat()
        if isinstance(obj, uuid.UUID): return str(obj)
        if hasattr(obj, 'to_dict') and callable(getattr(obj, 'to_dict')): return obj.to_dict()
        return super().default(obj)

class AppJSONDecoder(json.JSONDecoder):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(object_hook=self.object_hook, *args, **kwargs)
    def object_hook(self, dct: Dict[str, Any]) -> Any:
        for key, value in dct.items():
            if isinstance(value, str):
                if re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?([+-]\d{2}:\d{2}|Z)?', value):
                    try: dct[key] = datetime.fromisoformat(value); continue
                    except ValueError: pass
                if re.fullmatch(r'[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}', value):
                    try: dct[key] = uuid.UUID(value); continue
                    except ValueError: pass
        
        if 'job_id' in dct and 'selected_profile_id' in dct and 'source_directory' in dct : return JobState.from_dict(dct)
        elif 'file_id' in dct and 'original_path' in dct and 'status' in dct: return ProcessedFile.from_dict(dct)
        elif 'id' in dct and 'name' in dct and 'ffmpeg_params' in dct and 'applies_to_mkv_only' in dct and 'copy_tags' in dct: # Sprawdź RepairProfile
            return RepairProfile.from_dict(dct)
        elif 'id' in dct and 'name' in dct and 'ffmpeg_params' in dct and 'output_extension' in dct:
            return EncodingProfile.from_dict(dct)
        elif 'file_path' in dct and ('duration' in dct or 'error_message' in dct or 'video_codec' in dct or 'format_name' in dct or 'bit_rate' in dct or 'frame_rate' in dct):
             return MediaInfo.from_dict(dct)
        return dct
