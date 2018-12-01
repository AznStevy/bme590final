import json
import base64
import datetime
from pymodm import connect
from pymodm import MongoModel, fields

from processing import Processing


class Image(MongoModel):
    image_id = fields.CharField(primary_key=True)
    image = fields.ImageField()
    user_id = fields.CharField()
    timestamp = fields.DateTimeField()
    width = fields.IntegerField()
    height = fields.IntegerField()
    format = fields.CharField()
    description = fields.CharField()
    child_ids = fields.ListField()  # can have multiple children.
    process_history = fields.ListField()  # log of all previous IDs
    processing_time = fields.IntegerField()  # in milliseconds
    process = fields.CharField()  # the actual process that was done.


class User(MongoModel):
    user_id = fields.CharField(primary_key=True)
    # the structure of this will be key (upload id): most recent_id
    uploads = fields.DictField()


class ImageProcessingDB(object):
    def __init__(self):
        with open("config.json", 'r') as f:
            config_info = json.load(f)
            db_user = config_info["mongo_user"]
            db_pass = config_info["mongo_pass"]

            url = "mongodb://{}:{}@mongodb://<dbuser>:<dbpassword>" \
                  "@ds133378.mlab.com:33378/" \
                  "image_processing".format(db_user, db_pass)
            connect(url)

    def add_image(self, user_id, image_info):
        """
        Adds image to the database. First checks if it is a child of
        another image, then adds the image.
        Args:
            user_id: User who is adding the image.
            image_info: Information about the image.

        Returns:
            object: Image database object  that was added.
        """
        image_info = self._image_parameter_check(image_info)
        current_time = datetime.datetime.now()

        # see if there is a parent-child relationship for the image.
        if "parent_id" in image_info.keys():
            # look for the provided id in the database
            parent_image = self.find_image(image_info["parent_id"])
            process_history = parent_image.process_history
            process_history.append(image_info["parent_id"])
            # relate the child to the parent
            self._add_child(image_info["image_id"], image_info["parent_id"])
        else:
            process_history = []

        # update user object as well.
        self.update_user_uploads(user_id, process_history)

        # deal with tags
        if "description" not in image_info.keys():
            description = "None"
        else:
            description = image_info["description"]

        i = Image(image_id=image_info["image_id"],
                  user_id=user_id,
                  timestamp=current_time,
                  width=image_info["width"],
                  height=image_info["height"],
                  format=image_info["format"],
                  processing_time=image_info["processing_time"],
                  process=image_info["process"],
                  description=description,
                  process_history=process_history
                  )
        i.save()

    def _add_child(self, child_id, parent_id):
        """
        Adds a child id to the parent image.
        Args:
            parent_id: id of the parent to add the child id to.
            child_id: child id to add.

        Returns:
            str: child id of the image that was added.
        """
        parent_image = self.find_image(parent_id)
        if parent_image is not None:
            parent_image.child_ids.append(child_id)
            parent_image.save()
            return child_id
        return None

    def _image_parameter_check(self, image_info):
        """
        Tests if image input is valid.
        Args:
            image_info: Image object with imformation regarding
            image and history.

        Returns:
            bool: Whether or not the image_info object is valid.

        """
        if not isinstance(image_info, dict):
            raise TypeError("image_info must be type dict.")
        if "image_id" not in image_info.keys():
            raise AttributeError("image_info must have image_id.")
        if not isinstance(image_info["image_id"], str):
            raise AttributeError("image_id must be type str.")
        if "image" not in image_info.keys():
            raise AttributeError("image_info must have image data.")
        if not self._is_base64(image_info["image"]):
            raise TypeError("image must be type base64.")
        if "height" not in image_info.keys():
            raise AttributeError("image_info must have height.")
        if "width" not in image_info.keys():
            raise AttributeError("image_info must have width.")
        if not isinstance(image_info["height"], int):
            raise TypeError("height must be type int.")
        if not isinstance(image_info["width"], int):
            raise TypeError("height must be type int.")
        if "format" not in image_info.keys():
            raise AttributeError("image_info must have format.")
        if image_info["format"] != str:
            raise TypeError("format must be type str")
        if image_info["format"].lower() not in ["jpg", "jpeg", "png",
                                                "tiff", "gif"]:
            raise ValueError("format invalid.")
        if "processing_time" not in image_info.keys():
            raise AttributeError("image_info must have processing_time.")
        if not isinstance(image_info["processing_time"], int):
            raise TypeError(
                "processing_time must be type int in milliseconds.")
        if "process" not in image_info.keys():
            raise AttributeError("image_info must have process.")
        if not isinstance(image_info["process"], str):
            raise TypeError("process must be type str.")
        if not self.valid_process(image_info["process"]):
            raise ValueError("process invalid.")
        return image_info

    def valid_process(self, process):
        valid_processes = [method_name for method_name in dir(object)
                           if callable(getattr(Processing, method_name))]

        if process not in valid_processes:
            return False
        return True

    def add_user(self, user_id):
        """
        Adds user to the database.
        Args:
            user_id: Unique identifier. Doesn't have to be ID.

        Returns:
            object: user object that was saved.

        """
        test_user = self.find_user(user_id)
        if test_user:
            raise ValueError("User already exists!")

        u = User(user_id=user_id)
        u.save()
        return u

    def update_user_uploads(self, user_id, process_history: list):
        """
        Updates user uploads for an image.
        Args:
            process_history: History of Image ids.
            user_id: User to update.
        """
        root_id = process_history[0]
        recent_id = process_history[-1]
        user = self.find_user(user_id)
        if user is None:
            user = self.add_user(user_id)
        user.uploads[root_id] = recent_id
        user.save()

    def update_description(self, image_id, description: str):
        """
        Updates description of the image.
        Args:
            image_id: ID of image to update.
            description: Description to update with.

        Returns:
            bool: If the edit was successful.

        """
        image_exists = False
        # query = {"image_id": image_id}
        for image in Image.objects.all():
            if str(image.image_id) == image_id:
                image.heart_rates = description
                image.save()
                image_exists = True
        return image_exists

    def _is_base64(self, image_data: str):
        """
        Determines if the image is base64.
        Args:
            image_data: Image to be tested.

        Returns:
            bool: Whether or not the image data is base64.

        """
        try:
            return base64.b64encode(base64.b64decode(image_data)) == image_data
        except Exception:
            return False

    def remove_image(self, image_id):
        """
        Removes the image from the database.
        DANGER: will not remove parent-child relationship!
        Args:
            image_id: ID of the image to remove.
        """
        removed = False
        for image in Image.objects.all():
            if str(image.image_id) == image_id:
                removed = True
                image.delete()
        return removed

    def find_image(self, image_id):
        """
        Finds the image in the database based on image id.
        Args:
            image_id: ID of the image to find.

        Returns:
            object: found image in the database.
        """
        for image in Image.objects.all():
            if str(image.image_id) == image_id:
                return image
        return None

    def find_image_parent(self, image_id):
        """
        Finds the parent of the image in the database based on image id.
        Args:
            image_id: ID of the image to find.

        Returns:
            object: found image in the database.
        """
        image = self.find_image(image_id)
        parent_id = image.process_history[-1]
        parent_image = self.find_image(parent_id)
        return parent_image

    def find_image_child(self, image_id):
        """
        Finds the child of the image in the database based on image id.
        Args:
            image_id: ID of the image to find.

        Returns:
            object: found image in the database.
        """
        for image in Image.objects.all():
            if str(image.image_id) == image_id:
                return image
        return None

    def find_user(self, user_id):
        """
        Finds user in the database and returns if found.
        Args:
            user_id: ID of user to find.

        Returns:
            object: found user in the database.

        """
        for user in User.objects.all():
            if str(user.user_id) == user_id:
                return user
        return None