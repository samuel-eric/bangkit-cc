from fastapi import APIRouter, Form, UploadFile, File, HTTPException, Query
from typing import Annotated
from sqlmodel import SQLModel, select
from datetime import datetime

from ..models import Songs, Song_Likes
from ..dependencies.auth import CurrentUser
from ..dependencies.db import SessionDep
from ..dependencies.cloud_storage import BucketDep
from ..bucket_functions import upload_file, delete_file
from ..response_models import Response, AlbumPublic, UserPublic, SongPublic

router = APIRouter(prefix="/songs", tags=["songs"])


class SongCreate(SQLModel):
    name: str
    singer_id: int
    album_id: int
    likes: int
    popularity: float
    genre: str
    danceability: float
    loudness: float
    acousticness: float
    instrumentalness: float
    tempo: float
    key: str
    duration: int
    cover: str
    cover_url: str
    song: str
    song_url: str


class SongUpdate(SQLModel):
    name: str | None = None
    genre: str | None = None
    cover: str | None = None
    cover_url: str | None = None


class SongDelete(SQLModel):
    id: int
    created_at: datetime
    updated_at: datetime
    name: str
    like_count: int
    singer: UserPublic
    album: AlbumPublic


class SongLikeCreate(SQLModel):
    user_id: int
    song_id: int


@router.get("/", response_model=list[SongPublic])
async def get_all_songs(
    user_id: int,
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    itemPerPage: Annotated[int, Query(ge=10, le=30)] = 10,
):
    offset = (page - 1) * itemPerPage
    songs = session.exec(
        select(Songs)
        .where(Songs.singer_id == user_id)
        .order_by(Songs.created_at.desc())
        .offset(offset)
        .limit(itemPerPage)
    ).all()
    return songs


@router.get("/{song_id}", response_model=SongPublic)
async def get_song(song_id: int, session: SessionDep):
    song = session.get(Songs, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    return song


@router.post("/", response_model=SongPublic)
async def create_song(
    name: Annotated[str, Form(min_length=3)],
    album_id: Annotated[str | None, Form()],
    genre: Annotated[str, Form()],
    song: Annotated[UploadFile, File()],
    cover: Annotated[UploadFile, File()],
    current_user: CurrentUser,
    session: SessionDep,
    bucket: BucketDep,
):
    allowed_song_types = ["audio/mpeg", "audio/mp3", "audio/wav"]
    allowed_cover_types = ["image/jpeg", "image/png"]

    if (
        song.content_type not in allowed_song_types
        and cover.content_type not in allowed_cover_types
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file types: song - {song.content_type}, cover - {cover.content_type}. "
            f"Allowed song types: {', '.join(allowed_song_types)}, "
            f"Allowed cover types: {', '.join(allowed_cover_types)}",
        )
    elif song.content_type not in allowed_song_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid song file type: {song.content_type}. Allowed types: {', '.join(allowed_song_types)}",
        )
    elif cover.content_type not in allowed_cover_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid cover file type: {cover.content_type}. Allowed types: {', '.join(allowed_cover_types)}",
        )

    existing_song = session.exec(
        select(Songs).where(Songs.name == name, Songs.singer_id == current_user.id)
    ).one_or_none()
    if existing_song:
        raise HTTPException(
            status_code=400,
            detail="Song with the same name and singer has already been created",
        )

    try:
        folder_song = "song_file"
        folder_cover = "song_cover"
        song_blob_name, song_public_url = upload_file(
            bucket, current_user.id, song, folder_song
        )
        cover_blob_name, cover_public_url = upload_file(
            bucket, current_user.id, cover, folder_cover
        )

        song_data = SongCreate(
            name=name,
            singer_id=current_user.id,
            album_id=album_id,
            likes=0,
            popularity=0,
            genre=genre,
            danceability=0,
            loudness=0,
            acousticness=0,
            instrumentalness=0,
            tempo=0,
            key="",
            duration=0,
            cover=cover_blob_name,
            cover_url=cover_public_url,
            song=song_blob_name,
            song_url=song_public_url,
        )
        db_song = Songs.model_validate(song_data)
        session.add(db_song)
        session.commit()
        session.refresh(db_song)
        return db_song
    except Exception as e:
        session.rollback()
        if song_blob_name:
            delete_file(bucket, song_blob_name)
        if cover_blob_name:
            delete_file(bucket, cover_blob_name)
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


@router.put("/{song_id}", response_model=SongPublic)
async def update_song(
    song_id: int,
    session: SessionDep,
    current_user: CurrentUser,
    bucket: BucketDep,
    name: Annotated[str | None, Form()] = None,
    genre: Annotated[str | None, Form()] = None,
    cover: Annotated[UploadFile | None, File()] = None,
):
    song_db = session.get(Songs, song_id)
    if not song_db:
        raise HTTPException(status_code=404, detail="Song not found")
    if song_db.singer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot update another user's song")

    allowed_cover_types = ["image/jpeg", "image/png"]
    if cover.content_type not in allowed_cover_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {cover.content_type}. Allowed types: {', '.join(allowed_cover_types)}",
        )

    existing_song = session.exec(
        select(Songs).where(Songs.name == name, Songs.singer_id == current_user.id)
    ).one_or_none()
    if existing_song:
        raise HTTPException(
            status_code=400,
            detail="Song with the same name and singer has already been created",
        )

    try:
        folder_cover = "song_cover"
        song = SongUpdate()
        if cover is not None:
            cover_blob_name, public_url = upload_file(
                bucket, current_user.id, cover, folder_cover
            )

            delete_file(bucket, song.cover)

            song.cover = cover_blob_name
            song.cover_url = public_url
        if name is not None:
            song_db.name = name
        if genre is not None:
            song_db.genre = genre

        session.add(song_db)
        session.commit()
        session.refresh(song_db)
        return song_db
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


@router.delete("/{song_id}", response_model=SongDelete)
async def delete_song(
    song_id: int, session: SessionDep, current_user: CurrentUser, bucket: BucketDep
):
    song_db = session.get(Songs, song_id)
    if not song_db:
        raise HTTPException(status_code=404, detail="Song not found")
    if song_db.singer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot delete another user's song")

    try:
        delete_file(bucket, song_db.song_url)
        if song_db.cover_url:
            delete_file(bucket, song_db.cover_url)

        session.delete(song_db)
        session.commit()
        return song_db
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


@router.post("/{song_id}/like")
async def like_or_unlike_song(
    song_id: int, session: SessionDep, current_user: CurrentUser
):
    song = session.get(Songs, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    already_liked = session.exec(
        select(Song_Likes).where(
            Song_Likes.user_id == current_user.id, Song_Likes.song_id == song_id
        )
    ).one_or_none()
    if already_liked is not None:
        session.delete(already_liked)
        song.like_count -= 1
        session.add(song)

        session.commit()
        return Response(detail=f"Successfully unliked song with id {song_id}")
    else:
        song_like = SongLikeCreate(user_id=current_user.id, song_id=song_id)
        song_like_db = Song_Likes.model_validate(song_like)
        session.add(song_like_db)

        song.like_count += 1
        session.add(song)

        session.commit()
        return Response(detail=f"Successfully liked song with id {song_id}")
